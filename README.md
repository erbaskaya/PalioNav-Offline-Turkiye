# Palio Nav Offline Builder v5

This build is for an Android car multimedia unit and contains all Turkey offline map packages in the APK.

## Why v5

v4 built successfully but could crash immediately on some multimedia units. v5 changes the startup architecture:

- Uses OsmAnd `r5.4` release branch instead of moving `master`/nightly sources.
- Uses the `androidFull` flavor instead of `nightlyFree`.
- A lightweight Palio installer screen is now the launcher.
- OsmAnd MapActivity is not opened until the seven Turkey maps are extracted.
- After extraction, a dedicated `:restart` helper restarts the main process so maps are indexed cleanly from startup.
- Manifest edits use XML parsing instead of fragile text matching.
- Keeps both ARMv7 (32-bit) and ARM64 support in one APK.

## Build

1. Upload all files in this ZIP to the GitHub repository, replacing the old builder files.
2. Open **Actions**.
3. Run **Build Palio Nav Offline APK**.
4. Download the artifact **PalioNav-Offline-Turkiye-v5**.
5. Extract the artifact ZIP and copy `PalioNav-Offline-Turkiye.apk` to USB.

## Important clean-install step

Before testing v5 on the multimedia unit:

1. Uninstall the old **Palio Nav**.
2. Reboot the multimedia unit once.
3. Install the v5 APK.
4. On first launch, wait for the Palio Nav map preparation screen to finish. Do not close the app during map extraction.

The first run needs several GB of free internal storage because the APK itself and the extracted OBF maps coexist on the device.

## Expected first launch

The first screen should show:

- PALIO NAV
- Turkey Offline Navigation
- A progress bar
- Map preparation 1/7 ... 7/7

After completion the app restarts into the map.

## If it still closes immediately

If Android shows "Palio Nav keeps stopping" before the PALIO NAV progress screen appears, the failure is happening in the OsmAnd application/native startup layer rather than the map installer. In that case record the multimedia Android version, CPU/ABI and RAM, or test the official OsmAnd 5.4 APK on the same unit to isolate device compatibility.
