package com.smartsubmit.test;
import android.content.*;
public class AlarmReceiver extends BroadcastReceiver {
 @Override public void onReceive(Context c,Intent i){if ("android.intent.action.BOOT_COMPLETED".equals(i.getAction()) || "android.intent.action.MY_PACKAGE_REPLACED".equals(i.getAction())) { Schedule.next(c); return; } boolean live=i.getBooleanExtra("live",false); if(live) Schedule.next(c); if(!live||Schedule.allowed(c)) c.startForegroundService(new Intent(c,TestService.class).putExtra("live",live));}
}
