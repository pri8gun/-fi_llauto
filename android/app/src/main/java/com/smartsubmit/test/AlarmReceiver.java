package com.smartsubmit.test;
import android.content.*;
public class AlarmReceiver extends BroadcastReceiver {
 @Override public void onReceive(Context c,Intent i){c.startForegroundService(new Intent(c,TestService.class));}
}
