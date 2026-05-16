package com.reverie.myapp;

import android.os.Bundle;
import androidx.activity.EdgeToEdge;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(CalendarBridgePlugin.class);
        EdgeToEdge.enable(this);
        super.onCreate(savedInstanceState);
    }
}
