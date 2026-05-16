package com.reverie.myapp;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.provider.CalendarContract;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

@CapacitorPlugin(name = "CalendarBridge")
public class CalendarBridgePlugin extends Plugin {
    private static final long DEFAULT_EVENT_DURATION_MS = 30L * 60L * 1000L;

    @PluginMethod
    public void addEvent(PluginCall call) {
        String title = clean(call.getString("title"), "Reverie reminder");
        String description = clean(call.getString("description"), "");
        Long startMs = parseTime(call.getString("startIso"));
        Long endMs = parseTime(call.getString("endIso"));

        if (startMs == null) {
            call.reject("startIso is required and must be an ISO datetime.");
            return;
        }
        if (endMs == null || endMs <= startMs) {
            endMs = startMs + DEFAULT_EVENT_DURATION_MS;
        }

        Intent intent = new Intent(Intent.ACTION_INSERT)
            .setData(CalendarContract.Events.CONTENT_URI)
            .putExtra(CalendarContract.Events.TITLE, title)
            .putExtra(CalendarContract.Events.DESCRIPTION, description)
            .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, startMs)
            .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, endMs);

        try {
            getActivity().startActivity(intent);
            JSObject result = new JSObject();
            result.put("opened", true);
            call.resolve(result);
        } catch (ActivityNotFoundException ex) {
            call.reject("No calendar app is available on this device.", ex);
        } catch (Exception ex) {
            call.reject("Could not open the calendar app.", ex);
        }
    }

    private static String clean(String value, String fallback) {
        if (value == null) return fallback;
        String trimmed = value.trim();
        return trimmed.isEmpty() ? fallback : trimmed;
    }

    private static Long parseTime(String value) {
        String text = clean(value, "");
        if (text.isEmpty()) return null;
        String normalized = text.replace("Z", "+0000").replaceFirst("([+-]\\d{2}):(\\d{2})$", "$1$2");
        String[] patterns = {
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ",
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mmZ",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd'T'HH:mm"
        };
        for (String pattern : patterns) {
            try {
                SimpleDateFormat parser = new SimpleDateFormat(pattern, Locale.US);
                if (!pattern.endsWith("Z")) {
                    parser.setTimeZone(TimeZone.getDefault());
                }
                Date parsed = parser.parse(normalized);
                if (parsed != null) return parsed.getTime();
            } catch (ParseException ignored) {
            }
        }
        return null;
    }
}
