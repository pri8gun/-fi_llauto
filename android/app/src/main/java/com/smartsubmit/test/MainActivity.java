package com.smartsubmit.test;
import android.app.*;
import android.os.*;
import android.content.*;
import android.net.Uri;
import android.provider.Settings;
import android.widget.*;

public class MainActivity extends Activity {
 EditText name; TextView status;
 @Override public void onCreate(Bundle b) {
 super.onCreate(b);
 LinearLayout l=new LinearLayout(this); l.setOrientation(1); l.setPadding(28,36,28,28); setContentView(l);
 TextView title=new TextView(this); title.setText("SmartSubmit LIVE — 1.1\nBattery: keep Optimized."); title.setTextSize(22); l.addView(title);
 name=new EditText(this); name.setHint("Worker name"); name.setSingleLine(); name.setText(getPreferences(0).getString("name","")); l.addView(name);
 status=new TextView(this); l.addView(status);
 button(l,"Allow exact alarms",()->{if(Build.VERSION.SDK_INT>=31 && !getSystemService(AlarmManager.class).canScheduleExactAlarms()) startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,Uri.parse("package:"+getPackageName())));});
 button(l,"ENABLE AUTO SUBMIT",()->{if(!save())return; new AlertDialog.Builder(this).setTitle("Enable real submission?").setMessage("Disable Termux cron first. Enter your real worker name. Submit on scheduled working days from Nov 25, 2026.").setNegativeButton("Cancel",null).setPositiveButton("Enable",(d,w)->{getSharedPreferences("test",0).edit().putBoolean("enabled",true).commit();refresh();}).show();});
 button(l,"FILL & SUBMIT NOW",()->{if(!save())return;String day=java.time.LocalDate.now(Schedule.Z).toString();SharedPreferences prefs=getSharedPreferences("test",0);if(day.equals(prefs.getString("attempt",""))){new AlertDialog.Builder(this).setMessage(day.equals(prefs.getString("sent",""))?"Already confirmed today.":"Submission was attempted today; verify receipt before any retry.").setPositiveButton("OK",null).show();return;}new AlertDialog.Builder(this).setTitle("Submit today now?").setMessage("Confirm you are working today, the name is correct, and no form has already been sent by Termux or manually. This sends a real form even outside the automatic time window.").setNegativeButton("Cancel",null).setPositiveButton("Submit",(d,w)->startForegroundService(new Intent(this,TestService.class).putExtra("manual",true))).show();});
 button(l,"DISABLE AUTO SUBMIT",()->{getSharedPreferences("test",0).edit().putBoolean("enabled",false).commit();Schedule.cancel(this);refresh();});
 button(l,"Optional test in 2 minutes (no Submit)",()->{if(!save())return; AlarmManager a=getSystemService(AlarmManager.class); if(Build.VERSION.SDK_INT>=31&&!a.canScheduleExactAlarms()){status.setText("Allow exact alarms first");return;} PendingIntent p=PendingIntent.getBroadcast(this,1,new Intent(this,AlarmReceiver.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE); try{a.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP,SystemClock.elapsedRealtime()+120000,p);status.setText("Test scheduled in 2 minutes. Lock phone.");}catch(SecurityException e){status.setText("Alarm permission denied");}});
 button(l,"Refresh result",()->refresh());
 if(Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=0) requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},1);
 }
 boolean save(){String n=name.getText().toString().trim();if(n.isEmpty()){status.setText("Enter worker name");return false;}getPreferences(0).edit().putString("name",n).apply();getSharedPreferences("test",0).edit().putString("name",n).apply();return true;}
 void button(LinearLayout l,String text,Runnable r){Button b=new Button(this);b.setText(text);b.setOnClickListener(v->r.run());l.addView(b);}
 void refresh(){status.setText(Schedule.next(this)+"\n"+getSharedPreferences("test",0).getString("result","No submissions yet"));}
 @Override public void onResume(){super.onResume();if(status!=null)refresh();}
}
