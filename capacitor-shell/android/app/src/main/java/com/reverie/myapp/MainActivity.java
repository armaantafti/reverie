package com.reverie.myapp;

import android.content.ContentResolver;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.view.Window;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import androidx.activity.EdgeToEdge;
import com.getcapacitor.BridgeActivity;
import java.io.BufferedInputStream;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends BridgeActivity {
    private static final String HOSTED_APP_URL = "https://reverie-i2b8.onrender.com";
    private static final int SPLASH_DELAY_MS = 3000;
    private final ExecutorService shareUploadExecutor = Executors.newSingleThreadExecutor();

    @Override
    public void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        registerPlugin(CalendarBridgePlugin.class);
        registerPlugin(SpeechBridgePlugin.class);
        EdgeToEdge.enable(this);
        super.onCreate(savedInstanceState);
        if (getSupportActionBar() != null) {
            getSupportActionBar().hide();
        }
        showLaunchSplash();
        if (!handleReverieAuthIntent(getIntent())) {
            handleIncomingShareIntent(getIntent());
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (!handleReverieAuthIntent(intent)) {
            handleIncomingShareIntent(intent);
        }
    }

    private void showLaunchSplash() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(1, 6, 23));
        ImageView image = new ImageView(this);
        image.setImageResource(R.drawable.reverie_native_splash);
        image.setScaleType(ImageView.ScaleType.CENTER_CROP);
        root.addView(
            image,
            new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        );
        addContentView(
            root,
            new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        );
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            root.animate()
                .alpha(0f)
                .setDuration(260)
                .withEndAction(() -> {
                    ViewGroup parent = (ViewGroup) root.getParent();
                    if (parent != null) {
                        parent.removeView(root);
                    }
                })
                .start();
        }, SPLASH_DELAY_MS);
    }

    private boolean handleReverieAuthIntent(Intent intent) {
        if (intent == null || intent.getData() == null || this.bridge == null || this.bridge.getWebView() == null) {
            return false;
        }
        Uri data = intent.getData();
        if (!"reverie".equals(data.getScheme()) || !"auth".equals(data.getHost())) {
            return false;
        }

        String session = data.getQueryParameter("session");
        String error = data.getQueryParameter("error");
        final String targetUrl;
        if (session != null && !session.isEmpty()) {
            targetUrl = HOSTED_APP_URL + "/auth/native/complete?session=" + Uri.encode(session);
        } else if (error != null && !error.isEmpty()) {
            targetUrl = HOSTED_APP_URL + "/?auth_error=" + Uri.encode(error);
        } else {
            targetUrl = HOSTED_APP_URL + "/?auth_error=native_auth_missing";
        }
        this.bridge.getWebView().post(() -> this.bridge.getWebView().loadUrl(targetUrl));
        return true;
    }

    private void handleIncomingShareIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        String action = intent.getAction();
        if (!Intent.ACTION_SEND.equals(action) && !Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            return;
        }

        ArrayList<Uri> uris = new ArrayList<>();
        if (Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            ArrayList<Uri> sharedUris = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (sharedUris != null) {
                uris.addAll(sharedUris);
            }
        } else {
            Uri sharedUri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (sharedUri != null) {
                uris.add(sharedUri);
            }
        }

        if (uris.isEmpty()) {
            CharSequence sharedText = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
            if (sharedText != null) {
                loadHostedUrl(HOSTED_APP_URL + "/?shared_text=" + Uri.encode(sharedText.toString()));
            }
            return;
        }

        shareUploadExecutor.execute(() -> uploadSharedFiles(uris));
    }

    private void uploadSharedFiles(ArrayList<Uri> uris) {
        String boundary = "----ReverieShare" + System.currentTimeMillis();
        HttpURLConnection connection = null;
        try {
            URL url = new URL(HOSTED_APP_URL + "/notes/uploads");
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("POST");
            connection.setDoInput(true);
            connection.setDoOutput(true);
            connection.setUseCaches(false);
            connection.setConnectTimeout(30000);
            connection.setReadTimeout(120000);
            connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
            String cookie = CookieManager.getInstance().getCookie(HOSTED_APP_URL);
            if (cookie != null && !cookie.isEmpty()) {
                connection.setRequestProperty("Cookie", cookie);
            }

            try (DataOutputStream output = new DataOutputStream(connection.getOutputStream())) {
                for (Uri uri : uris) {
                    writeFilePart(output, boundary, uri);
                }
                output.writeBytes("--" + boundary + "--\r\n");
                output.flush();
            }

            int status = connection.getResponseCode();
            if (status >= 200 && status < 300) {
                loadHostedUrl(HOSTED_APP_URL + "/?share_upload=success");
            } else if (status == 401) {
                loadHostedUrl(HOSTED_APP_URL + "/?share_upload=login_required");
            } else {
                loadHostedUrl(HOSTED_APP_URL + "/?share_upload=failed");
            }
        } catch (Exception e) {
            loadHostedUrl(HOSTED_APP_URL + "/?share_upload=failed");
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private void writeFilePart(DataOutputStream output, String boundary, Uri uri) throws Exception {
        ContentResolver resolver = getContentResolver();
        String fileName = getDisplayName(uri);
        String mimeType = resolver.getType(uri);
        if (mimeType == null || mimeType.isEmpty()) {
            mimeType = "application/octet-stream";
        }
        output.writeBytes("--" + boundary + "\r\n");
        output.writeBytes("Content-Disposition: form-data; name=\"files\"; filename=\"" + sanitizeFileName(fileName) + "\"\r\n");
        output.writeBytes("Content-Type: " + mimeType + "\r\n\r\n");
        try (InputStream input = new BufferedInputStream(resolver.openInputStream(uri))) {
            if (input == null) {
                throw new IllegalStateException("Could not open shared file.");
            }
            byte[] buffer = new byte[8192];
            int bytesRead;
            while ((bytesRead = input.read(buffer)) != -1) {
                output.write(buffer, 0, bytesRead);
            }
        }
        output.writeBytes("\r\n");
    }

    private String getDisplayName(Uri uri) {
        String fallback = "shared-file";
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (nameIndex >= 0) {
                    String name = cursor.getString(nameIndex);
                    if (name != null && !name.trim().isEmpty()) {
                        return name.trim();
                    }
                }
            }
        } catch (Exception ignored) {}
        String lastPath = uri.getLastPathSegment();
        return lastPath == null || lastPath.trim().isEmpty() ? fallback : lastPath.trim();
    }

    private String sanitizeFileName(String fileName) {
        return fileName.replace("\\", "_").replace("\"", "_").replace("\r", "_").replace("\n", "_");
    }

    private void loadHostedUrl(String url) {
        if (this.bridge == null || this.bridge.getWebView() == null) {
            return;
        }
        this.bridge.getWebView().post(() -> this.bridge.getWebView().loadUrl(url));
    }
}
