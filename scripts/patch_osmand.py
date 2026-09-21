#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

if len(sys.argv) < 2:
    raise SystemExit("usage: patch_osmand.py <android-root> [map-bundle-version]")

root = Path(sys.argv[1]).resolve()
map_version = sys.argv[2] if len(sys.argv) > 2 else "2026-09"
osmand = root / "OsmAnd"


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"Could not patch {label}; upstream source changed")
    return text.replace(old, new, count)


def flavor_block(text: str, flavor: str) -> tuple[int, int, str]:
    marker = f"\t\t{flavor} {{"
    start = text.find(marker)
    if start < 0:
        marker = f"        {flavor} {{"
        start = text.find(marker)
    if start < 0:
        raise SystemExit(f"Could not find {flavor} flavor")
    brace = text.find("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1, text[start:i + 1]
    raise SystemExit(f"Could not parse {flavor} flavor")


# 1) Use the Android full flavor as the production-like base, not the nightly flavor.
build = osmand / "build.gradle"
text = build.read_text(encoding="utf-8")
start, end, block = flavor_block(text, "androidFull")
block = require_replace(block, 'applicationId "net.osmand.plus"', 'applicationId "com.baskaya.palionav"', "androidFull applicationId")
block = require_replace(block, 'resValue "string", "app_name", "OsmAnd~"', 'resValue "string", "app_name", "Palio Nav"', "androidFull app name")
text = text[:start] + block + text[end:]
build.write_text(text, encoding="utf-8")

# Do not recompress already-compressed map packages inside the APK.
common = osmand / "build-common.gradle"
text = common.read_text(encoding="utf-8")
if 'noCompress "qz", "zip"' not in text:
    text = require_replace(text, 'noCompress "qz"', 'noCompress "qz", "zip"', "APK noCompress")
common.write_text(text, encoding="utf-8")

# Ship Turkish TTS rules by default.
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

# 2) Manifest: use an XML parser so upstream indentation cannot break the patch.
ANDROID_URI = "http://schemas.android.com/apk/res/android"
TOOLS_URI = "http://schemas.android.com/tools"
A = "{" + ANDROID_URI + "}"
ET.register_namespace("android", ANDROID_URI)
ET.register_namespace("tools", TOOLS_URI)

manifest = osmand / "AndroidManifest.xml"
tree = ET.parse(manifest)
manifest_root = tree.getroot()
app_node = manifest_root.find("application")
if app_node is None:
    raise SystemExit("Could not find application in manifest")

map_activity = None
for node in app_node.findall("activity"):
    if node.get(A + "name") == "net.osmand.plus.activities.MapActivity":
        map_activity = node
        break
if map_activity is None:
    raise SystemExit("Could not find MapActivity in manifest")

map_activity.set(A + "screenOrientation", "landscape")

# Remove only the MAIN/LAUNCHER filter from MapActivity. Other deep-link filters stay.
removed_launcher = False
for intent_filter in list(map_activity.findall("intent-filter")):
    actions = {x.get(A + "name") for x in intent_filter.findall("action")}
    categories = {x.get(A + "name") for x in intent_filter.findall("category")}
    if "android.intent.action.MAIN" in actions and "android.intent.category.LAUNCHER" in categories:
        map_activity.remove(intent_filter)
        removed_launcher = True
if not removed_launcher:
    raise SystemExit("Could not find MapActivity MAIN/LAUNCHER filter")

# Fix FileProvider authority to follow our custom applicationId.
for provider in app_node.findall("provider"):
    if provider.get(A + "name") == "androidx.core.content.FileProvider":
        provider.set(A + "authorities", "${applicationId}.fileprovider")

# Add a lightweight launcher that installs maps before MapActivity is ever opened.
bootstrap_name = "net.osmand.plus.activities.PalioBootstrapActivity"
restart_name = "net.osmand.plus.activities.PalioRestartActivity"
for node in list(app_node.findall("activity")):
    if node.get(A + "name") in {bootstrap_name, restart_name}:
        app_node.remove(node)

bootstrap = ET.Element("activity")
bootstrap.set(A + "name", bootstrap_name)
bootstrap.set(A + "label", "@string/app_name")
bootstrap.set(A + "theme", "@android:style/Theme.Material.Light.NoActionBar.Fullscreen")
bootstrap.set(A + "screenOrientation", "landscape")
bootstrap.set(A + "launchMode", "singleTask")
bootstrap.set(A + "exported", "true")
launcher = ET.SubElement(bootstrap, "intent-filter")
ET.SubElement(launcher, "action").set(A + "name", "android.intent.action.MAIN")
ET.SubElement(launcher, "category").set(A + "name", "android.intent.category.LAUNCHER")
ET.SubElement(launcher, "category").set(A + "name", "android.intent.category.APP_MAPS")

restart = ET.Element("activity")
restart.set(A + "name", restart_name)
restart.set(A + "theme", "@android:style/Theme.Translucent.NoTitleBar")
restart.set(A + "process", ":restart")
restart.set(A + "excludeFromRecents", "true")
restart.set(A + "exported", "false")

children = list(app_node)
map_index = children.index(map_activity)
app_node.insert(map_index, bootstrap)
app_node.insert(map_index + 1, restart)

tree.write(manifest, encoding="utf-8", xml_declaration=True)

# 3) First-run installer. It is now the launcher, so MapActivity is not involved
# until all seven maps are present. After extraction we use a tiny :restart helper
# so OsmAnd starts a fresh process and indexes the new maps from startup.
java_dir = osmand / "src/net/osmand/plus/activities"
java_dir.mkdir(parents=True, exist_ok=True)

bootstrap_java = java_dir / "PalioBootstrapActivity.java"
bootstrap_java.write_text(f'''package net.osmand.plus.activities;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.res.AssetManager;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Process;
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
            File targetRoot = app.getAppPath(null);
            File[] maps = targetRoot.listFiles((dir, name) -> {{
                String n = name.toLowerCase(Locale.ROOT);
                return n.startsWith("turkey_") && n.endsWith(".obf");
            }});
            return maps == null || maps.length < EXPECTED_MAP_COUNT;
        }} catch (Throwable t) {{
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
            openMap();
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
        subtitle.setText("T\u00fcrkiye \u00c7evrimd\u0131\u015f\u0131 Navigasyon");
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
        status.setText("\u00c7evrimd\u0131\u015f\u0131 T\u00fcrkiye haritas\u0131 haz\u0131rlan\u0131yor...");
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(-1, -2);
        tp.topMargin = 20;
        root.addView(status, tp);

        TextView note = new TextView(this);
        note.setText("\u0130lk kurulumda haritalar APK i\u00e7inden cihaz belle\u011fine a\u00e7\u0131l\u0131r. \u0130nternet kullan\u0131lmaz.");
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
                    status.setText("T\u00fcrkiye haritas\u0131 haz\u0131rlan\u0131yor " + index + "/" + mapCount);
                    progress.setProgress(Math.max(1, (index - 1) * 100 / mapCount));
                }});

                try (InputStream raw = assets.open("palio_maps/" + f, AssetManager.ACCESS_STREAMING);
                     ZipInputStream zin = new ZipInputStream(new BufferedInputStream(raw, 1024 * 256))) {{
                    ZipEntry entry;
                    boolean extracted = false;
                    while ((entry = zin.getNextEntry()) != null) {{
                        try {{
                            if (entry.isDirectory() || !entry.getName().toLowerCase(Locale.ROOT).endsWith(".obf")) {{
                                continue;
                            }}
                            String safeName = new File(entry.getName()).getName();
                            File out = new File(targetRoot, safeName);
                            File part = new File(targetRoot, safeName + ".part");
                            if (part.exists()) part.delete();
                            copy(zin, part);
                            if (out.exists() && !out.delete()) {{
                                throw new IOException("Cannot replace " + out.getName());
                            }}
                            if (!part.renameTo(out)) {{
                                throw new IOException("Cannot finish " + out.getName());
                            }}
                            extracted = true;
                        }} finally {{
                            zin.closeEntry();
                        }}
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
                status.setText("Haz\u0131r. Navigasyon yeniden ba\u015flat\u0131l\u0131yor...");
                progress.setProgress(100);
            }});
            try {{ Thread.sleep(500); }} catch (InterruptedException ignored) {{ }}
            runOnUiThread(this::restartFresh);
        }} catch (Throwable e) {{
            runOnUiThread(() -> {{
                status.setText("Kurulum hatas\u0131: " + e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()) +
                        "\\nCihazda en az 3 GB bo\u015f alan oldu\u011fundan emin olun.");
                status.setTextColor(Color.rgb(255, 130, 130));
                progress.setVisibility(View.GONE);
            }});
        }}
    }}

    private static void copy(InputStream in, File out) throws IOException {{
        byte[] buffer = new byte[1024 * 1024];
        try (BufferedOutputStream bos = new BufferedOutputStream(new FileOutputStream(out), 1024 * 1024)) {{
            int n;
            while ((n = in.read(buffer)) != -1) {{
                if (n > 0) bos.write(buffer, 0, n);
            }}
            bos.flush();
        }}
    }}

    private void openMap() {{
        Intent intent = new Intent(this, MapActivity.class);
        intent.putExtra("show_osmand_welcome_screen", false);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(intent);
        finish();
    }}

    private void restartFresh() {{
        Intent intent = new Intent(this, PalioRestartActivity.class);
        intent.putExtra("main_pid", Process.myPid());
        startActivity(intent);
    }}
}}
''', encoding="utf-8")

restart_java = java_dir / "PalioRestartActivity.java"
restart_java.write_text('''package net.osmand.plus.activities;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Process;

public class PalioRestartActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        int mainPid = getIntent().getIntExtra("main_pid", -1);
        if (mainPid > 0 && mainPid != Process.myPid()) {
            Process.killProcess(mainPid);
        }
        Intent map = new Intent(this, MapActivity.class);
        map.putExtra("show_osmand_welcome_screen", false);
        map.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(map);
        finish();
        Runtime.getRuntime().exit(0);
    }
}
''', encoding="utf-8")

print("Patched OsmAnd r5.4 for Palio Nav v5")
print("Production-like androidFull flavor selected")
print("Bootstrap is the launcher; MapActivity starts only after map install")
print("Fresh-process restart helper installed")
print("Map bundle version:", map_version)
