package com.smartsubmit.test;
import android.app.*;
import android.os.*;
import android.content.*;
import android.webkit.*;
import org.json.*;
import java.time.*;
import java.time.format.DateTimeFormatter;

public class TestService extends Service {
 Handler h=new Handler(Looper.getMainLooper()); WebView web; PowerManager.WakeLock lock; boolean done; String values;
 NotificationManager nm; static final String URL="https://app.smartsheet.com/b/form/2bc79c969d504a948791cb84fcf751e7";
 @Override public IBinder onBind(Intent i){return null;}
 Notification notice(String s){return new Notification.Builder(this,"test").setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("SmartSubmit TEST").setContentText(s).setStyle(new Notification.BigTextStyle().bigText(s)).build();}
 @Override public int onStartCommand(Intent i,int flags,int id){
 if(web!=null)return START_NOT_STICKY;
 nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("test","SmartSubmit tests",NotificationManager.IMPORTANCE_HIGH));startForeground(1,notice("Testing — no submission"));
 lock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"smartsubmit:test");lock.acquire(90000);
 String name=getSharedPreferences("test",0).getString("name","");
 if(name.isEmpty()){finish("FAIL: name missing");return START_NOT_STICKY;}
 String date=LocalDate.now(ZoneId.of("America/Vancouver")).format(DateTimeFormatter.ofPattern("MM/dd/yyyy"));
 values=new JSONArray(java.util.Arrays.asList(name,"Dayshift","Craft","Mechanical","7:30",date)).toString();
 web=new WebView(this);web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);
 web.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){return !("https".equals(r.getUrl().getScheme())&&"app.smartsheet.com".equals(r.getUrl().getHost()));}});
 web.loadUrl(URL);h.postDelayed(()->poll(0),3000);h.postDelayed(()->finish("FAIL: timeout"),75000);
 return START_NOT_STICKY;
 }
 void poll(int attempt){if(done)return;if(attempt>20){finish("FAIL: form fields unavailable");return;}
 web.evaluateJavascript("(function(){return document.querySelectorAll('input[type=text]').length})()",r->{if(done)return;if(!r.matches("[0-9]+")||Integer.parseInt(r)<6){h.postDelayed(()->poll(attempt+1),2000);return;}fill();});}
 void fill(){String js="(function(){const v="+values+";const a=document.querySelectorAll('input[type=text]');const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;v.forEach((x,i)=>{const e=a[i];e.focus();s.call(e,x);for(const t of ['input','change'])e.dispatchEvent(new Event(t,{bubbles:true}));for(const t of ['keydown','keyup'])e.dispatchEvent(new KeyboardEvent(t,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));e.blur();});return true;})()";
 // Block form submission events and all outgoing POST requests are not guaranteed by WebView.
 // Avoid Enter on a real form: use input/change only, and intercept submit events.
 String safe=js.replace("for(const t of ['keydown','keyup'])e.dispatchEvent(new KeyboardEvent(t,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));","");
 web.evaluateJavascript("(function(){document.addEventListener('submit',e=>{e.preventDefault();e.stopImmediatePropagation();},true);})()",r->{if(!done)web.evaluateJavascript(safe,x->h.postDelayed(()->verify(),1500));});
 }
 void verify(){if(done)return;web.evaluateJavascript("(function(){const a=document.querySelectorAll('input[type=text]');const c=document.querySelectorAll('[role=combobox]');return [a[0]?.value.trim(),c[0]?.innerText.trim(),c[1]?.innerText.trim(),a[3]?.value.trim(),a[4]?.value.trim(),a[5]?.value.trim()];})()",r->{try{JSONArray actual=new JSONArray(r), expected=new JSONArray(values);boolean ok=true;for(int j=0;j<6;j++)ok &= expected.getString(j).equals(actual.optString(j));String[] labels={"Name","Dayshift","Craft","Mechanical","Time","Date"}; StringBuilder report=new StringBuilder(ok?"PASS: all 6 fields match; no Submit":"FAIL: field mismatch; no Submit"); for(int j=0;j<6;j++){report.append("\n").append(labels[j]).append(": ").append(expected.getString(j).equals(actual.optString(j))?"OK":(j==0?"MISMATCH (name hidden)":"expected "+expected.getString(j)+", got "+actual.optString(j)));} finish(report.toString());}catch(Exception e){finish("FAIL: cannot verify fields");}});}
 void finish(String result){if(done)return;done=true;String stamp=ZonedDateTime.now(ZoneId.of("America/Vancouver")).toString();getSharedPreferences("test",0).edit().putString("result",stamp+"\n"+result).apply();stopForeground(STOP_FOREGROUND_REMOVE);nm.notify(2,notice(result));stopSelf();}
 @Override public void onDestroy(){done=true;h.removeCallbacksAndMessages(null);if(web!=null){web.destroy();web=null;}if(lock!=null&&lock.isHeld())lock.release();super.onDestroy();}
}
