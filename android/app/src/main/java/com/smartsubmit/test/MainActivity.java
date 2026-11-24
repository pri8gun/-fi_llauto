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
 TextView title=new TextView(this); title.setText("SmartSubmit — TEST ONLY\nSubmit disabled. Battery: keep Optimized."); title.setTextSize(22); l.addView(title);
 name=new EditText(this); name.setHint("Worker name"); name.setSingleLine(); name.setText(getPreferences(0).getString("name","")); l.addView(name);
 status=new TextView(this); l.addView(status);
 button(l,"Allow exact alarms",()->{if(Build.VERSION.SDK_INT>=31 && !getSystemService(AlarmManager.class).canScheduleExactAlarms()) startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,Uri.parse("package:"+getPackageName())));});
 button(l,"Test now (no Submit)",()->{if(save()) startForegroundService(new Intent(this,TestService.class));});
 button(l,"Test in 2 minutes (lock screen)",()->{if(!save())return; AlarmManager a=getSystemService(AlarmManager.class); if(Build.VERSION.SDK_INT>=31&&!a.canScheduleExactAlarms()){status.setText("Allow exact alarms first");return;} PendingIntent p=PendingIntent.getBroadcast(this,1,new Intent(this,AlarmReceiver.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE); try{a.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP,SystemClock.elapsedRealtime()+120000,p);status.setText("Test scheduled in 2 minutes. Lock phone.");}catch(SecurityException e){status.setText("Alarm permission denied");}});
 button(l,"Refresh result",()->refresh());
 if(Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=0) requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},1);
 }
 boolean save(){String n=name.getText().toString().trim();if(n.isEmpty()){status.setText("Enter worker name");return false;}getPreferences(0).edit().putString("name",n).apply();getSharedPreferences("test",0).edit().putString("name",n).apply();return true;}
 void button(LinearLayout l,String text,Runnable r){Button b=new Button(this);b.setText(text);b.setOnClickListener(v->r.run());l.addView(b);}
 void refresh(){status.setText(getSharedPreferences("test",0).getString("result","No tests yet"));}
 @Override public void onResume(){super.onResume();if(status!=null)refresh();}
}
