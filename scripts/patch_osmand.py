#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) < 2:
    raise SystemExit("usage: patch_osmand.py <android-root> [map-bundle-version]")

root = Path(sys.argv[1]).resolve()
map_version = sys.argv[2] if len(sys.argv) > 2 else "2026-09"
osmand = root / "OsmAnd"

build = osmand / "build.gradle"
text = build.read_text(encoding="utf-8")
text = text.replace('applicationId "net.osmand.dev"', 'applicationId "com.baskaya.palionav"', 1)
text = text.replace('resValue "string", "app_name", "OsmAnd Nightly"', 'resValue "string", "app_name", "Palio Nav"', 1)
build.write_text(text, encoding="utf-8")

common = osmand / "build-common.gradle"
text = common.read_text(encoding="utf-8")
text = text.replace('noCompress "qz"', 'noCompress "qz", "zip"', 1)
common.write_text(text, encoding="utf-8")


resources = root.parent / "resources" / "bundled_assets.json"
if resources.exists():
    rtext = resources.read_text(encoding="utf-8")
    tr_block_old = """{
            "source": "voice/tr/tr_tts.js",
            "destination": "voice/tr-tts/tr_tts.js",
            "mode": "overwriteOnlyIfExists"
        }"""
    tr_block_new = tr_block_old.replace("overwriteOnlyIfExists", "alwaysOverwriteOrCopy")
    rtext = rtext.replace(tr_block_old, tr_block_new, 1)
    resources.write_text(rtext, encoding="utf-8")

manifest = osmand / "AndroidManifest.xml"
text = manifest.read_text(encoding="utf-8")
text = text.replace('android:screenOrientation="unspecified" android:launchMode="singleTask"',
                    'android:screenOrientation="landscape" android:launchMode="singleTask"', 1)
launcher = '''\n<intent-filter>\n<action android:name="android.intent.action.MAIN" />\n<category android:name="android.intent.category.LAUNCHER" />\n<category android:name="android.intent.category.MULTIWINDOW_LAUNCHER" />\n<category android:name="android.intent.category.APP_MAPS" />\n</intent-filter>\n'''
if launcher not in text:
    raise SystemExit("Could not find MapActivity launcher intent filter; upstream manifest changed")
text = text.replace(launcher, "\n", 1)
needle = '<activity android:name="net.osmand.plus.activities.MapActivity"'
bootstrap = '''<activity android:name="net.osmand.plus.activities.PalioBootstrapActivity"
android:label="Palio Nav"
android:theme="@style/FirstSplashScreenPlus"
android:screenOrientation="landscape"
android:exported="true">
<intent-filter>
<action android:name="android.intent.action.MAIN" />
<category android:name="android.intent.category.LAUNCHER" />
<category android:name="android.intent.category.APP_MAPS" />
</intent-filter>
</activity>

'''
if needle not in text:
    raise SystemExit("Could not find MapActivity declaration; upstream manifest changed")
text = text.replace(needle, bootstrap + needle, 1)
manifest.write_text(text, encoding="utf-8")

java_dir = osmand / "src/net/osmand/plus/activities"
java_dir.mkdir(parents=True, exist_ok=True)
java = java_dir / "PalioBootstrapActivity.java"
java.write_text(f'''package net.osmand.plus.activities;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.res.AssetManager;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import net.osmand.plus.OsmandApplication;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Palio Nav first-run bootstrapper.
 * Installs the Turkey OBF map packages bundled in assets/palio_maps and then
 * restarts OsmAnd so the normal resource scanner sees every map offline.
 */
public class PalioBootstrapActivity extends Activity {{
    private static final String PREFS = "palionav_bootstrap";
    private static final String KEY_VERSION = "installed_map_bundle";
    private static final String MAP_BUNDLE_VERSION = "{map_version}";

    private TextView status;
    private ProgressBar progress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN |
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        setContentView(buildUi());

        if (mapsAlreadyInstalled()) {{
            openMap();
        }} else {{
            new Thread(this::installBundledMaps, "palio-map-installer").start();
        }}
    }}

    private View buildUi() {{
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(48, 32, 48, 32);
        root.setBackgroundColor(Color.rgb(12, 18, 26));

        TextView title = new TextView(this);
        title.setText("PALIO NAV");
        title.setTextColor(Color.WHITE);
        title.setTextSize(32);
        title.setGravity(Gravity.CENTER);
        root.addView(title, new LinearLayout.LayoutParams(-1, -2));

        TextView subtitle = new TextView(this);
        subtitle.setText("Türkiye Çevrimdışı Navigasyon");
        subtitle.setTextColor(Color.rgb(170, 190, 210));
        subtitle.setTextSize(17);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(-1, -2);
        sp.topMargin = 10;
        root.addView(subtitle, sp);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgress(0);
        LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(-1, 24);
        pp.topMargin = 36;
        root.addView(progress, pp);

        status = new TextView(this);
        status.setText("Çevrimdışı haritalar hazırlanıyor…");
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(-1, -2);
        tp.topMargin = 20;
        root.addView(status, tp);

        TextView note = new TextView(this);
        note.setText("İlk kurulum sırasında ekranı kapatmayın. İnternet bağlantısı kullanılmaz.");
        note.setTextColor(Color.rgb(145, 160, 175));
        note.setTextSize(14);
        note.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams np = new LinearLayout.LayoutParams(-1, -2);
        np.topMargin = 18;
        root.addView(note, np);
        return root;
    }}

    private boolean mapsAlreadyInstalled() {{
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (!MAP_BUNDLE_VERSION.equals(prefs.getString(KEY_VERSION, ""))) {{
            return false;
        }}
        File root = ((OsmandApplication) getApplication()).getAppPath(null);
        File[] maps = root.listFiles((dir, name) -> name.toLowerCase(Locale.ROOT).startsWith("turkey_")
                && name.toLowerCase(Locale.ROOT).endsWith(".obf"));
        return maps != null && maps.length >= 7;
    }}

    private void installBundledMaps() {{
        try {{
            AssetManager assets = getAssets();
            String[] files = assets.list("palio_maps");
            if (files == null) {{
                throw new IOException("palio_maps asset directory is missing");
            }}
            Arrays.sort(files);
            int total = 0;
            for (String f : files) {{
                if (f.endsWith(".obf.zip")) total++;
            }}
            if (total < 7) {{
                throw new IOException("Turkey map bundle is incomplete: " + total + "/7");
            }}
            final int mapCount = total;

            File targetRoot = ((OsmandApplication) getApplication()).getAppPath(null);
            if (!targetRoot.exists() && !targetRoot.mkdirs()) {{
                throw new IOException("Cannot create map directory: " + targetRoot);
            }}

            int done = 0;
            for (String f : files) {{
                if (!f.endsWith(".obf.zip")) continue;
                final int index = ++done;
                runOnUiThread(() -> {{
                    status.setText("Türkiye haritası hazırlanıyor " + index + "/" + mapCount);
                    progress.setProgress(Math.max(1, (index - 1) * 100 / mapCount));
                }});
                try (InputStream raw = assets.open("palio_maps/" + f, AssetManager.ACCESS_STREAMING);
                     ZipInputStream zin = new ZipInputStream(new BufferedInputStream(raw, 1024 * 256))) {{
                    ZipEntry entry;
                    boolean extracted = false;
                    while ((entry = zin.getNextEntry()) != null) {{
                        if (entry.isDirectory() || !entry.getName().toLowerCase(Locale.ROOT).endsWith(".obf")) {{
                            zin.closeEntry();
                            continue;
                        }}
                        String safeName = new File(entry.getName()).getName();
                        File out = new File(targetRoot, safeName);
                        File part = new File(targetRoot, safeName + ".part");
                        copy(zin, part);
                        if (out.exists() && !out.delete()) {{
                            throw new IOException("Cannot replace " + out.getName());
                        }}
                        if (!part.renameTo(out)) {{
                            throw new IOException("Cannot finish " + out.getName());
                        }}
                        extracted = true;
                        zin.closeEntry();
                    }}
                    if (!extracted) {{
                        throw new IOException("No .obf inside " + f);
                    }}
                }}
                final int pct = done * 100 / mapCount;
                runOnUiThread(() -> progress.setProgress(pct));
            }}

            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString(KEY_VERSION, MAP_BUNDLE_VERSION)
                    .apply();
            runOnUiThread(() -> {{
                status.setText("Hazır. Navigasyon açılıyor…");
                progress.setProgress(100);
            }});
            try {{ Thread.sleep(350); }} catch (InterruptedException ignored) {{ }}
            runOnUiThread(() -> RestartActivity.doRestartSilent(this));
        }} catch (Exception e) {{
            runOnUiThread(() -> {{
                status.setText("Kurulum hatası: " + e.getMessage() + "\nCihazda en az 3 GB boş alan olduğundan emin olun.");
                status.setTextColor(Color.rgb(255, 130, 130));
                progress.setVisibility(View.GONE);
            }});
        }}
    }}

    private static void copy(InputStream in, File out) throws IOException {{
        byte[] buffer = new byte[1024 * 1024];
        try (BufferedOutputStream bos = new BufferedOutputStream(new FileOutputStream(out), 1024 * 1024)) {{
            int n;
            while ((n = in.read(buffer)) > 0) {{
                bos.write(buffer, 0, n);
            }}
            bos.flush();
        }}
    }}

    private void openMap() {{
        startActivity(new Intent(this, MapActivity.class));
        finish();
    }}
}}
''', encoding="utf-8")

print("Patched OsmAnd for Palio Nav")
print("Map bundle version:", map_version)
