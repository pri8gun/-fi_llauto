package com.smartsubmit.test;
import android.app.*;
import android.content.*;
import android.os.Build;
import java.time.*;

public class Schedule {
 static final ZoneId Z=ZoneId.of("America/Vancouver");
 static boolean work(LocalDate d){return (!d.isBefore(LocalDate.of(2026,11,25))&&!d.isAfter(LocalDate.of(2026,12,1)))||(!d.isBefore(LocalDate.of(2026,12,9))&&!d.isAfter(LocalDate.of(2026,12,22)));}
 static boolean allowed(Context c){return c.getSharedPreferences("test",0).getBoolean("enabled",false)&&work(LocalDate.now(Z));}
 static boolean window(){LocalTime t=LocalTime.now(Z);return !t.isBefore(LocalTime.of(7,0))&&t.isBefore(LocalTime.of(7,36));}
 static PendingIntent pending(Context c){return PendingIntent.getBroadcast(c,42,new Intent(c,AlarmReceiver.class).putExtra("live",true),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
 static void cancel(Context c){c.getSystemService(AlarmManager.class).cancel(pending(c));}
 static String next(Context c){
 AlarmManager a=c.getSystemService(AlarmManager.class);cancel(c);
 if(!c.getSharedPreferences("test",0).getBoolean("enabled",false))return "Disabled";
 if(Build.VERSION.SDK_INT>=31&&!a.canScheduleExactAlarms())return "Exact alarms permission required";
 ZonedDateTime now=ZonedDateTime.now(Z);
 String attempt=c.getSharedPreferences("test",0).getString("attempt","");
 for(int offset=0;offset<40;offset++){LocalDate d=now.toLocalDate().plusDays(offset);if(!work(d)||attempt.equals(d.toString()))continue;
 for(int m=0;m<=35;m+=5){ZonedDateTime t=d.atTime(7,m).atZone(Z);if(!t.isAfter(now))continue;
 try{a.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,t.toInstant().toEpochMilli(),pending(c));return "Next: "+t.toLocalDate()+" "+t.toLocalTime()+" Vancouver";}catch(SecurityException ex){return "Exact alarms permission denied";}}}
 return "No remaining dates in 2026 schedule";
 }
}
