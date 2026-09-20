#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) < 2:
    raise SystemExit("usage: patch_osmand.py <android-root> [map-bundle-version]")

root = Path(sys.argv[1]).resolve()
map_version = sys.argv[2] if len(sys.argv) > 2 else "2026-09"
osmand = root / "OsmAnd"


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"Could not patch {label}; upstream source changed")
    return text.replace(old, new, count)


# 1) Brand the nightly build that our workflow compiles.
build = osmand / "build.gradle"
text = build.read_text(encoding="utf-8")
text = require_replace(
    text,
    'applicationId "net.osmand.dev"',
    'applicationId "com.baskaya.palionav"',
    "nightly applicationId",
)
text = require_replace(
    text,
    'resValue "string", "app_name", "OsmAnd Nightly"',
    'resValue "string", "app_name", "Palio Nav"',
    "app name",
)
build.write_text(text, encoding="utf-8")

# Keep the already-compressed OBF zip assets stored instead of compressing them again.
common = osmand / "build-common.gradle"
text = common.read_text(encoding="utf-8")
if 'noCompress "qz", "zip"' not in text:
    text = require_replace(text, 'noCompress "qz"', 'noCompress "qz", "zip"', "APK noCompress")
common.write_text(text, encoding="utf-8")

# Make Turkish TTS rules available by default when OsmAnd resources are merged.
resources = root.parent / "resources" / "bundled_assets.json"
if resources.exists():
    rtext = resources.read_text(encoding="utf-8")
    old = '''{
            "source": "voice/tr/tr_tts.js",
            "destination": "voice/tr-tts/tr_tts.js",
            "mode": "overwriteOnlyIfExists"
        }'''
    new = old.replace("overwriteOnlyIfExists", "alwaysOverwriteOrCopy")
    if old in rtext:
        rtext = rtext.replace(old, new, 1)
        resources.write_text(rtext, encoding="utf-8")

# 2) Manifest: DO NOT touch OsmAnd's launcher intent-filter anymore.
# v1/v2 failed because they depended on the exact upstream launcher block.
manifest = osmand / "AndroidManifest.xml"
text = manifest.read_text(encoding="utf-8")

# Force the normal map activity to landscape for the car multimedia screen.
if 'android:screenOrientation="landscape"' not in text:
    text = require_replace(
        text,
        'android:screenOrientation="unspecified"',
        'android:screenOrientation="landscape"',
        "MapActivity landscape orientation",
    )

# Avoid authority collision if another OsmAnd variant exists on the device.
text = text.replace(
    'android:authorities="net.osmand.plus.fileprovider"',
    'android:authorities="${applicationId}.fileprovider"',
    1,
)

activity_marker = '<activity android:name="net.osmand.plus.activities.MapActivity"'
activity_pos = text.find(activity_marker)
if activity_pos < 0:
    raise SystemExit("Could not find MapActivity declaration; upstream manifest changed")

bootstrap_decl = '''<activity android:name="net.osmand.plus.activities.PalioBootstrapActivity"
\t\t\tandroid:label="@string/app_name"
\t\t\tandroid:theme="@style/FirstSplashScreenPlus"
\t\t\tandroid:screenOrientation="landscape"
\t\t\tandroid:exported="false" />

\t\t'''
if 'android:name="net.osmand.plus.activities.PalioBootstrapActivity"' not in text:
    text = text[:activity_pos] + bootstrap_decl + text[activity_pos:]
manifest.write_text(text, encoding="utf-8")

# 3) Put a very small gate into MapActivity. MapActivity remains the launcher.
# On the very first run it opens our installer activity, which extracts the seven
# embedded Turkey OBF packages in a background thread, then restarts OsmAnd.
map_activity_file = osmand / "src/net/osmand/plus/activities/MapActivity.java"
map_text = map_activity_file.read_text(encoding="utf-8")
gate = '''\n\t\tif (PalioBootstrapActivity.needsMapInstall(this)) {\n\t\t\tstartActivity(new android.content.Intent(this, PalioBootstrapActivity.class));\n\t\t\tfinish();\n\t\t\treturn;\n\t\t}\n'''
if "PalioBootstrapActivity.needsMapInstall(this)" not in map_text:
    anchor = '\t\tsuper.onCreate(savedInstanceState);\n'
    if anchor not in map_text:
        raise SystemExit("Could not patch MapActivity onCreate; upstream source changed")
    map_text = map_text.replace(anchor, anchor + gate, 1)
    map_activity_file.write_text(map_text, encoding="utf-8")

# 4) First-run map installer.
java_dir = osmand / "src/net/osmand/plus/activities"
java_dir.mkdir(parents=True, exist_ok=True)
java = java_dir / "PalioBootstrapActivity.java"
java.write_text(f'''package net.osmand.plus.activities;

import android.app.Activity;
import android.content.Context;
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
 * First-run installer for the Turkey map bundle embedded in the Palio Nav APK.
 * The normal OsmAnd MapActivity remains the launcher; it redirects here only
 * until all seven OBF files have been installed.
 */
public class PalioBootstrapActivity extends Activity {{
    private static final String PREFS = "palionav_bootstrap";
    private static final String KEY_VERSION = "installed_map_bundle";
    private static final String MAP_BUNDLE_VERSION = "{map_version}";
    private static final int EXPECTED_MAP_COUNT = 7;

    private TextView status;
    private ProgressBar progress;

    public static boolean needsMapInstall(Context context) {{
        SharedPreferences prefs = context.getSharedPreferences(PREFS, MODE_PRIVATE);
        if (!MAP_BUNDLE_VERSION.equals(prefs.getString(KEY_VERSION, ""))) {{
            return true;
        }}
        try {{
            OsmandApplication app = (OsmandApplication) context.getApplicationContext();
            File root = app.getAppPath(null);
            File[] maps = root.listFiles((dir, name) -> {{
                String n = name.toLowerCase(Locale.ROOT);
                return n.startsWith("turkey_") && n.endsWith(".obf");
            }});
            return maps == null || maps.length < EXPECTED_MAP_COUNT;
        }} catch (Exception e) {{
            return true;
        }}
    }}

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

        if (!needsMapInstall(this)) {{
            restartIntoMap();
            return;
        }}
        new Thread(this::installBundledMaps, "palio-map-installer").start();
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
        status.setText("Çevrimdışı Türkiye haritası hazırlanıyor…");
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(-1, -2);
        tp.topMargin = 20;
        root.addView(status, tp);

        TextView note = new TextView(this);
        note.setText("İlk kurulumda yaklaşık 1 GB harita cihaz içine hazırlanır. İnternet kullanılmaz.");
        note.setTextColor(Color.rgb(145, 160, 175));
        note.setTextSize(14);
        note.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams np = new LinearLayout.LayoutParams(-1, -2);
        np.topMargin = 18;
        root.addView(note, np);
        return root;
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
            if (total < EXPECTED_MAP_COUNT) {{
                throw new IOException("Turkey map bundle is incomplete: " + total + "/" + EXPECTED_MAP_COUNT);
            }}
            final int mapCount = total;

            OsmandApplication app = (OsmandApplication) getApplication();
            File targetRoot = app.getAppPath(null);
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

            app.getSettings().SHOW_OSMAND_WELCOME_SCREEN.set(false);
            app.getSettings().MAP_SCREEN_ORIENTATION.set(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString(KEY_VERSION, MAP_BUNDLE_VERSION)
                    .commit();

            runOnUiThread(() -> {{
                status.setText("Hazır. Navigasyon açılıyor…");
                progress.setProgress(100);
            }});
            try {{ Thread.sleep(350); }} catch (InterruptedException ignored) {{ }}
            runOnUiThread(this::restartIntoMap);
        }} catch (Exception e) {{
            runOnUiThread(() -> {{
                status.setText("Kurulum hatası: " + e.getMessage() + "\\nCihazda en az 3 GB boş alan olduğundan emin olun.");
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

    private void restartIntoMap() {{
        RestartActivity.doRestartSilent(this);
    }}
}}
''', encoding="utf-8")

print("Patched OsmAnd for Palio Nav v3")
print("Launcher intent-filter left untouched")
print("MapActivity first-run gate installed")
print("Map bundle version:", map_version)
