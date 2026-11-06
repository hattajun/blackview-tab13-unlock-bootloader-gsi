# Blackview Tab 13 (MT6769 / Helio G85): bootloader unlock and Android 13 GSI

[日本語版はこちら / Japanese](README.ja.md)

Notes on unlocking the bootloader of the **Blackview Tab 13** (MediaTek MT6768/MT6769, Helio G85) and booting a **TrebleDroid Android 13 GSI** on it, including what went wrong on the way. I could not find any custom ROM, TWRP or GSI report for this tablet, so this is written down for the next person.

> **Disclaimer**
> This is a personal log, with no warranty. Unlocking the bootloader erases all data, a mistake can leave the device unbootable, and it may void your warranty. Do everything at your own risk and **back up first**.
> Results are from a single unit. Other batches or firmware versions may behave differently.

## Summary

| Item | Result |
|---|---|
| Bootloader unlock | Success (`fastboot flashing unlock`) |
| TrebleDroid Android 13 GSI | Boots |
| Verified working | Wi-Fi, cameras, audio, brightness, auto-rotate, touch, charging and battery level |
| Not tested | Bluetooth, GPS, fingerprint/face unlock, SIM / mobile data, USB OTG, resume from sleep, idle battery drain |

**The key finding:** the usual GSI step `fastboot --disable-verity --disable-verification flash vbmeta ...` applied to all three of `vbmeta`, `vbmeta_system` and `vbmeta_vendor` made **both the GSI and the stock system fail to boot** (stock recovery: "Can't load Android system", reason `init_user0_failed`). Setting only the **main `vbmeta`** to "hashtree disabled only" (flags = 1) and leaving the other two stock booted fine. See [What went wrong](#5-what-went-wrong).

## Device and environment

- Device: Blackview Tab 13 (`ro.product.model=Tab 13`, device `Tab_13`)
- SoC: MediaTek MT6768/MT6769 (Helio G85, `k68v1`), `ro.board.platform=mt6768`
- Stock OS: Android 12 (`Blackview/Tab_13/Tab_13:12/SP1A.210812.016/1737343939:user/release-keys`), kernel 4.19.191
- Partitioning: A-only (not A/B) + dynamic partitions (`super`, ~7.3 GB), Treble enabled (`ro.treble.enabled=true`, VNDK 31), arm64
- Host: Ubuntu 24.04, Python 3.12
- Tools: [mtkclient](https://github.com/bkerler/mtkclient), `adb` / `fastboot` (Ubuntu packages)
- GSI: [TrebleDroid](https://github.com/TrebleDroid/treble_experimentations/releases) `ci-20230905` (`android_13.0.0_r73`), `system-td-arm64-ab-vanilla.img.xz`

## Overview

1. Detect the tablet with mtkclient (Preloader mode)
2. Back up the partitions
3. Unlock the bootloader with fastboot
4. Flash the GSI (mind the `vbmeta` flags)
5. If it does not boot: recover (reach fastbootd through `misc`)

Helper scripts are in [`scripts/`](scripts/).

## 0. Host setup

```bash
# mtkclient in a virtualenv
git clone --depth 1 https://github.com/bkerler/mtkclient.git
python3 -m venv venv
./venv/bin/pip install -r mtkclient/requirements.txt
./venv/bin/pip install ./mtkclient

# udev rules (needs sudo)
sudo cp mtkclient/Setup/Linux/*.rules /etc/udev/rules.d/
sudo udevadm control -R && sudo udevadm trigger

# adb / fastboot
sudo apt install adb fastboot
```

mtkclient's chip table already contains `MT6768/MT6769` (hwcode `0x707`).

## 1. Detecting the tablet (Preloader mode)

With the tablet **powered off**, plugging in USB makes it show up as a Preloader for only a few seconds (on Windows, "MT65xx Preloader" flashes in Device Manager). mtkclient can catch that window:

1. Start the command on the PC first, so it is already waiting.
2. Plug in the powered-off tablet **without holding any button**.

```bash
./venv/bin/mtk printgpt   # prints the GPT, read-only
```

What it reported:

- `CPU: MT6768/MT6769(Helio P65/G85 k68v1)`, `HW code: 0x707`
- `SBC enabled: False`, `SLA enabled: False`, `DAA enabled: False`
  → no signed-DA authentication, so partitions can be read and written.
- `0e8d:2000 MediaTek Inc. MT65xx Preloader` in `lsusb`

### Tips

- No buttons for Preloader mode. If nothing happens, hold a volume key while connecting to try BROM.
- Always start `mtk` **before** plugging in; the window is short.
- Use a USB 2.0 port directly on the PC (no hub). A cable pulled out mid-transfer ends the run.

## 2. Backup

### 2.1 Small partitions in one go

```bash
mkdir -p backup && cd backup
../venv/bin/mtk rl . --skip super,userdata,cache
# the preloader lives in a separate area (boot1)
../venv/bin/mtk r preloader preloader.bin --parttype boot1
```

Dumped: `lk`, `lk2`, `seccfg`, `boot`, `vendor_boot`, `recovery`, `dtbo`, `vbmeta*`, `persist`, `nvdata`, `nvram`, `nvcfg`, `proinfo`, `protect1/2`, `md1img`, and the GPT.

### 2.2 `super` (~7.3 GB), in chunks

A single `mtk r super super.bin` disconnected at ~6%. Reading **1 GiB at a time** with `mtk ro <offset> <length> <file>` went through in a single connection.

`super` is at user-area offset `0x2c000000`, length `0x1b2800000` (from `printgpt`). [`scripts/dump_super.sh`](scripts/dump_super.sh) is a resumable version of this (completed chunks are skipped):

```bash
MTK=./venv/bin/mtk ./scripts/dump_super.sh backup
```

After concatenation I checked that the size is `0x1b2800000` (7,289,700,352 bytes) and that the LP geometry magic (`67446c61`, "alpg") is at `0x1000`. Then record checksums with `sha256sum *.bin`.

> `userdata` (internal storage) is not backed up. The unlock wipes it, so copy anything you need off the tablet first.

## 3. Unlocking the bootloader

### 3.1 `mtkclient`'s seccfg unlock did not work

```bash
./venv/bin/mtk da seccfg unlock
# -> "Device has is either already unlocked or algo is unknown. Aborting."
```

`seccfg` is version 4 with `lock_state=1` (default = locked). It was not already unlocked: mtkclient could not handle this device's hash scheme and aborted **without writing anything**.

### 3.2 The regular fastboot unlock worked

1. Boot normally, tap Settings → About tablet → Build number 7 times to enable developer options.
2. Enable "OEM unlocking" and "USB debugging".
3. Run:

```bash
adb devices                            # accept the authorization prompt
adb reboot bootloader
fastboot getvar unlocked               # unlocked: no
fastboot flashing get_unlock_ability   # unlock_ability = 16777216 (0x01000000)
fastboot flashing unlock               # WIPES ALL DATA
```

- It takes about 77 s, and **you must confirm on the tablet's screen with Volume Up**.
- Afterwards `fastboot getvar unlocked` → `unlocked: yes`.
- `fastboot reboot` brings up the setup wizard. A bootloader-unlocked warning is shown on every boot.
- After boot: `ro.boot.flash.locked=0`, `verifiedbootstate=orange`, `vbmeta.device_state=unlocked`.

## 4. Installing the GSI

### 4.1 Choosing the GSI

- TrebleDroid only ships `ab` images; there is no A-only build. This tablet is system-as-root with dynamic partitions, and `arm64-ab-vanilla` booted.
- The kernel is 4.19, so I stayed on the last Android 13 build, `ci-20230905`, and avoided Android 14+.
- Size: the extracted image is 1,931,804,672 bytes, about 4.2 MiB larger than the stock `system` (`0x72E12000` = 1,927,356,416 bytes), so `system` has to be grown. `super` is ~7.3 GB, so there is room without deleting `product`.

```bash
curl -L -O https://github.com/TrebleDroid/treble_experimentations/releases/download/ci-20230905/system-td-arm64-ab-vanilla.img.xz
xz -t system-td-arm64-ab-vanilla.img.xz
xz -dk system-td-arm64-ab-vanilla.img.xz
```

### 4.2 Preparing `vbmeta` (the important part)

Make the **main `vbmeta`** carry only **flags = 1 (`HASHTREE_DISABLED`)**. The AVB flags are a big-endian u32 at offset 120 of the header. [`scripts/make_vbmeta_flag1.py`](scripts/make_vbmeta_flag1.py) does this:

```bash
python3 scripts/make_vbmeta_flag1.py backup/vbmeta.bin vbmeta_flag1.bin
```

Leave `vbmeta_system` and `vbmeta_vendor` **stock**.

You can write it with mtkclient directly in Preloader mode (no fastbootd needed):

```bash
./venv/bin/mtk w vbmeta vbmeta_flag1.bin
```

### 4.3 Flash `system` from fastbootd

Logical partitions inside `super` are written from fastbootd (`adb reboot fastboot` works too if USB debugging is on).

```bash
fastboot reboot fastboot
fastboot getvar is-userspace                         # yes
fastboot resize-logical-partition system 2147483648  # grow to 2 GiB
fastboot flash system system-td-arm64-ab-vanilla.img
fastboot erase userdata
fastboot erase metadata
fastboot reboot
```

It is flashed as 8 sparse chunks in about a minute. After the first boot, the TrebleDroid boot animation led straight to the Android 13 home screen.

## 5. What went wrong

### 5.1 Symptom

After flashing the GSI the tablet dropped into the stock recovery: "Can't load Android system. Your data may be corrupt...", with only "Try again" and "Factory data reset". A factory reset did not help.

### 5.2 Narrowing it down

- I first suspected the `product` partition I had deleted (it is mounted in first-stage init). I recreated it and flashed the stock `product.img`; no change.
- **Getting logs:** `adb` in this recovery is `unauthorized`. The `cache` partition (ext4) holds the recovery log (`last_log`), so I dumped it and ran `strings`:
  ```bash
  ./venv/bin/mtk r cache cache.bin
  strings -n 6 cache.bin | grep -E "Command: |reason"
  # Command: "/system/bin/recovery" "--prompt_and_wipe_data" "--reason=init_user0_failed"
  ```
  → Android got part-way through boot and failed initialising user 0 (`init_user0`). No kernel panic.
- **The stock `system` failed the same way**, so it was not the GSI; it was the `vbmeta` setup.
- Restoring the three original `vbmeta` images made the stock system boot.

### 5.3 Conclusion

| `vbmeta` setup | Result |
|---|---|
| Original (verification on) | Stock boots |
| All three with `--disable-verity --disable-verification` (flags = 3) | GSI **and** stock **fail** (`init_user0_failed`) |
| Main `vbmeta` flags = 1, the other two stock | Stock **and** GSI **boot** |

Disabling verification is the trigger. My guess is that the TEE/keymaster depends on the verified-boot state, but **that is a guess and untested**.

## 6. Recovery

### 6.1 When you cannot reach fastboot (stuck in recovery)

If the hardware keys do not get you into fastboot, **write a bootloader message (BCB) to `misc` that asks for fastbootd on the next boot**. The recovery then comes up in fastbootd. [`scripts/make_misc_fastboot.py`](scripts/make_misc_fastboot.py) builds the image:

```bash
python3 scripts/make_misc_fastboot.py backup/misc.bin misc_fastboot.bin
./venv/bin/mtk w misc misc_fastboot.bin   # start it, then plug in the powered-off tablet
# then power the tablet on: it enters fastbootd
```

In a reboot loop the Preloader window opens every cycle, so `mtk` can catch it.

### 6.2 Going back to stock

- Restore `vbmeta`, `vbmeta_system`, `vbmeta_vendor` from your backup.
- Restore `system` (and `product` / `vendor` if needed) from images extracted out of your `super.bin` dump with [`scripts/lp_extract.py`](scripts/lp_extract.py), or write the whole `super.bin` back.

```bash
python3 scripts/lp_extract.py backup/super.bin stock_extract system vendor product
```

## 7. Partition layout (`printgpt`)

`recovery`, `misc`, `para`, `expdb`, `frp`, `vbmeta`, `vbmeta_system`, `vbmeta_vendor`, `md_udc`, `metadata`, `nvcfg`, `nvdata`, `persist`, `protect1/2`, `seccfg`, `sec1`, `proinfo`, `boot_para`, `nvram`, `logo`, `md1img`, `spmfw`, `scp1/2`, `sspm_1/2`, `gz1/2`, `lk`, `lk2`, `boot`, `vendor_boot`, `dtbo`, `tee1/2`, `super` (7.3 GB at `0x2c000000`), `cache`, `userdata`, `otp`, `flashinfo`.

Logical partitions in `super`: `system`, `vendor`, `product`. Stock sizes: `system` = `0x72E12000`, `vendor` = `0x1E56F000`, `product` = `0x8182F000`.

## 8. Notes

- I found no custom ROM (LineageOS etc.) or TWRP reports for the Tab 13 in the searches I ran.
- Useful sources: Hovatek forum threads for various Blackview devices, mtkclient's README, TrebleDroid (phhusson) releases, Android's GSI documentation.
- I did not try re-locking the bootloader, so this log does not cover it.

## 9. Open items

- Bluetooth, GPS, fingerprint/face unlock, SIM / mobile data, USB OTG, resume from sleep, idle battery drain.
- Rooting (patching `boot.img` with Magisk).
- Why flags = 1 works and flags = 3 does not (only a guess so far).
- Other GSIs (crDroid, etc.) and Android 14+ GSIs.

## Privacy note for anyone sharing dumps

Never publish your `backup/` directory. `persist`, `nvdata`, `nvram`, `proinfo` and similar partitions hold device-unique data (IMEI, MAC addresses, calibration, keys). The included `.gitignore` excludes them.
