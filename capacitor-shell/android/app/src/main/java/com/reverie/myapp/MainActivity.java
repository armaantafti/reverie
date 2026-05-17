package com.reverie.myapp;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Window;
import androidx.activity.EdgeToEdge;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private static final String HOSTED_APP_URL = "https://reverie-i2b8.onrender.com";

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
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleReverieAuthIntent(intent);
    }

    private void handleReverieAuthIntent(Intent intent) {
        if (intent == null || intent.getData() == null || this.bridge == null || this.bridge.getWebView() == null) {
            return;
        }
        Uri data = intent.getData();
        if (!"reverie".equals(data.getScheme()) || !"auth".equals(data.getHost())) {
            return;
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
    }
}
