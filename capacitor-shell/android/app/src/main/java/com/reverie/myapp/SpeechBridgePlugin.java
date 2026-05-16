package com.reverie.myapp;

import android.Manifest;
import android.content.Intent;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

@CapacitorPlugin(
    name = "SpeechBridge",
    permissions = {
        @Permission(alias = "microphone", strings = { Manifest.permission.RECORD_AUDIO })
    }
)
public class SpeechBridgePlugin extends Plugin {
    @PluginMethod
    public void start(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "microphonePermissionCallback");
            return;
        }
        startListening(call);
    }

    @PermissionCallback
    private void microphonePermissionCallback(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            call.reject("Microphone permission was denied.");
            return;
        }
        startListening(call);
    }

    private void startListening(PluginCall call) {
        if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
            call.reject("Speech recognition is not available on this device.");
            return;
        }

        getActivity().runOnUiThread(() -> {
            SpeechRecognizer recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
            AtomicBoolean finished = new AtomicBoolean(false);

            Runnable cleanup = () -> {
                try {
                    recognizer.cancel();
                    recognizer.destroy();
                } catch (Exception ignored) {
                }
            };

            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) {}
                @Override public void onBeginningOfSpeech() {}
                @Override public void onRmsChanged(float rmsdB) {}
                @Override public void onBufferReceived(byte[] buffer) {}
                @Override public void onEndOfSpeech() {}
                @Override public void onPartialResults(Bundle partialResults) {}
                @Override public void onEvent(int eventType, Bundle params) {}

                @Override
                public void onError(int error) {
                    if (!finished.compareAndSet(false, true)) return;
                    cleanup.run();
                    String message = error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT
                        ? "No speech detected. Try again."
                        : "Voice input could not start on this device.";
                    call.reject(message);
                }

                @Override
                public void onResults(Bundle results) {
                    if (!finished.compareAndSet(false, true)) return;
                    ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    String transcript = matches != null && !matches.isEmpty() ? matches.get(0) : "";
                    cleanup.run();
                    JSObject payload = new JSObject();
                    payload.put("transcript", transcript == null ? "" : transcript.trim());
                    call.resolve(payload);
                }
            });

            String language = call.getString("language", Locale.getDefault().toLanguageTag());
            Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, language);
            intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);

            try {
                recognizer.startListening(intent);
            } catch (Exception ex) {
                cleanup.run();
                call.reject("Voice input could not start on this device.", ex);
            }
        });
    }
}
