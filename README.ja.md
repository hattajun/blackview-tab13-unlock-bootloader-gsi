# Blackview Tab 13 (MT6769 / Helio G85) ブートローダーアンロックと GSI (Android 13) 導入メモ

[English version](README.md)

Blackview Tab 13 のブートローダーをアンロックし、TrebleDroid の Android 13 GSI を起動させるまでの手順と、途中で詰まった点の記録です。この機種のカスタム ROM / TWRP / GSI の情報は見つからなかったので、次の人のために残します。補助スクリプトは [`scripts/`](scripts/) にあります。

> **免責**
> 個人の作業記録であり、動作の保証はありません。ブートローダーのアンロックはデータを全消去し、手順を誤ると端末が起動しなくなります。保証が無効になる可能性もあります。すべて自己責任で、**必ず先にバックアップを取ってください**。
> 本メモは自分の端末 1 台での結果です。同じ型番でも、ロットやファームウェアのバージョンで挙動が異なる可能性があります。

## 結果の概要

| 項目 | 結果 |
|---|---|
| ブートローダーアンロック | 成功（`fastboot flashing unlock`） |
| TrebleDroid Android 13 GSI | 起動成功 |
| Google アプリ（[7 章](#7-google-アプリの追加play-ストアyoutubegmailマップ)） | MindTheGapps を組み込むと動作: Google ログイン、Play ストア、YouTube、Gmail、マップ、Chrome のインストールと動作を確認。「端末が認定されていません」の警告は出なかった |
| 動作確認 OK | Wi-Fi、Bluetooth、カメラ、音、輝度変更、自動回転、タッチ、充電・バッテリー残量表示 |
| 怪しい | GPS（安定して動いていなさそう。未調査） |
| 未確認 | 指紋・顔認証、SIM／モバイル通信、USB OTG、スリープ復帰、待機中の消費電力、銀行・決済アプリ、DRM 動画（アンロック状態のため動かない可能性が高い） |

**最大のポイント:** GSI 導入時、定番の `fastboot --disable-verity --disable-verification flash vbmeta ...` を `vbmeta` / `vbmeta_system` / `vbmeta_vendor` の 3 つすべてに行うと、**GSI でもストックでも起動に失敗**しました（リカバリで "Can't load Android system"、理由 `init_user0_failed`）。メインの `vbmeta` だけに「hashtree 無効のみ（フラグ 1）」を設定すると起動しました。詳細は「5. 失敗と原因」を参照してください。

## 端末・環境

- 端末: Blackview Tab 13（`ro.product.model=Tab 13` / device `Tab_13`）
- SoC: MediaTek MT6768/MT6769（Helio G85、`k68v1`）、`ro.board.platform=mt6768`
- 出荷時 OS: Android 12（`Blackview/Tab_13/Tab_13:12/SP1A.210812.016/1737343939:user/release-keys`）、カーネル 4.19.191
- パーティション構成: A-only（A/B ではない）＋動的パーティション（`super`、約 7.3 GB）、Treble 対応（`ro.treble.enabled=true`、VNDK 31）、arm64
- PC: Ubuntu 24.04（Linux）、Python 3.12
- 使用ツール: [mtkclient](https://github.com/bkerler/mtkclient)、`adb` / `fastboot`（Ubuntu の `adb` `fastboot` パッケージ）
- GSI: [TrebleDroid](https://github.com/TrebleDroid/treble_experimentations/releases) の `ci-20230905`（`android_13.0.0_r73`）の `system-td-arm64-ab-vanilla.img.xz`

## 全体の流れ

1. mtkclient で端末を検出する（Preloader モード）
2. パーティションをバックアップする
3. fastboot でブートローダーをアンロックする
4. GSI を書き込む（`vbmeta` のフラグに注意）
5. 起動しなかった場合の復旧（`misc` 経由で fastbootd に入る）
6. 任意: GSI イメージに MindTheGapps を組み込んで、Google アプリ（Play ストアなど）を追加する

## 0. 準備（PC 側）

```bash
# mtkclient（venv に導入）
git clone --depth 1 https://github.com/bkerler/mtkclient.git
python3 -m venv venv
./venv/bin/pip install -r mtkclient/requirements.txt
./venv/bin/pip install ./mtkclient

# udev ルール（sudo が必要）
sudo cp mtkclient/Setup/Linux/*.rules /etc/udev/rules.d/
sudo udevadm control -R && sudo udevadm trigger

# adb / fastboot
sudo apt install adb fastboot
```

mtkclient のチップ設定には `MT6768/MT6769`（hwcode `0x707`）が含まれていました。

## 1. 端末の検出（Preloader モード）

この端末は、**電源オフの状態で USB を接続すると、Preloader として数秒だけ現れます**（Windows ではデバイスマネージャーに "MT65xx Preloader" が一瞬見えます）。mtkclient はこの窓を捕まえられます。

1. 先に PC 側でコマンドを実行して、待機状態にします。
2. 電源オフのタブレットを、ボタンを押さずに USB 接続します。

```bash
./venv/bin/mtk printgpt   # GPT を表示するだけ（読み取りのみ）
```

出力で確認できた内容:

- `CPU: MT6768/MT6769(Helio P65/G85 k68v1)`、`HW code: 0x707`
- `SBC enabled: False` / `SLA enabled: False` / `DAA enabled: False`
  → 署名認証なしで DA（Download Agent）が使え、パーティションの読み書きができます。
- `0e8d:2000 MediaTek Inc. MT65xx Preloader`（`lsusb`）

### 検出のコツ

- ボタンは押さずに接続します（Preloader モード）。反応がなければ、音量キーを押しながら接続して BROM を試します。
- 接続の**前に** `mtk` を待機させておきます（窓が短いため）。
- USB 2.0 の PC 背面ポートに直結し、ハブを避けます。
- 長時間の転送中にケーブルが抜けたり切断されたりすると失敗します。

## 2. バックアップ

### 2-1. 小さいパーティションを一括でダンプ

```bash
mkdir -p backup && cd backup
../venv/bin/mtk rl . --skip super,userdata,cache
# preloader は別領域（boot1）
../venv/bin/mtk r preloader preloader.bin --parttype boot1
```

取得できた主なもの: `lk`、`lk2`、`seccfg`、`boot`、`vendor_boot`、`recovery`、`dtbo`、`vbmeta*`、`persist`、`nvdata`、`nvram`、`nvcfg`、`proinfo`、`protect1/2`、`md1img`、GPT。

### 2-2. `super`（約 7.3 GB）は分割してダンプ

一括（`mtk r super super.bin`）では、約 6% の地点で USB が切断され失敗しました。**1 GiB ずつの分割ダンプ**にすると、1 回の接続で最後まで通りました。

`super` はユーザー領域のオフセット `0x2c000000`、長さ `0x1b2800000` です（`printgpt` の値）。

```bash
#!/bin/bash
# dump_super.sh: 再開可能な分割ダンプ。完了済みチャンクはスキップする
OUT=backup/super_chunks; mkdir -p "$OUT"
START=$((0x2c000000)); TOTAL=$((0x1b2800000)); CH=$((0x40000000))
i=0; off=0
while [ $off -lt $TOTAL ]; do
  len=$CH; [ $((TOTAL-off)) -lt $CH ] && len=$((TOTAL-off))
  f=$(printf "%s/super.%02d.bin" "$OUT" $i)
  if [ -f "$f" ] && [ "$(stat -c %s "$f")" -eq "$len" ]; then
    echo "chunk $i already done"
  else
    rm -f "$f"
    timeout 900 ./venv/bin/mtk ro $(printf 0x%x $((START+off))) $(printf 0x%x $len) "$f"
    [ "$(stat -c %s "$f" 2>/dev/null)" -eq "$len" ] || { echo "chunk $i FAILED"; rm -f "$f"; exit 1; }
  fi
  off=$((off+len)); i=$((i+1))
done
cat "$OUT"/super.0*.bin > backup/super.bin
```

結合後、サイズが `0x1b2800000`（7,289,700,352 バイト）であること、`0x1000` の位置に LP メタデータのジオメトリのマジック（`67446c61`）があることを確認しました。最後に `sha256sum *.bin` でチェックサムを残しておきます。

> `userdata`（内部ストレージ）はバックアップしていません。アンロックで消えるので、必要なデータは先にタブレット側で退避してください。

## 3. ブートローダーのアンロック

### 3-1. mtkclient の `seccfg` アンロックは失敗した

```bash
./venv/bin/mtk da seccfg unlock
# -> "Device has is either already unlocked or algo is unknown. Aborting."
```

`seccfg` はバージョン 4、`lock_state=1`（デフォルト＝ロック）で、アンロック済みではなく、mtkclient がこの端末のハッシュ方式を扱えず中止しました（`seccfg` は書き換わっていません）。

### 3-2. 標準の fastboot 手順で成功

1. タブレットを通常起動し、設定 → タブレット情報 → ビルド番号を 7 回タップして開発者オプションを有効にします。
2. 開発者オプションで「OEM ロック解除」と「USB デバッグ」を有効にします。
3. 次を実行します。

```bash
adb devices                      # 認証ダイアログで許可
adb reboot bootloader
fastboot getvar unlocked         # unlocked: no
fastboot flashing get_unlock_ability   # unlock_ability = 16777216 (0x01000000)
fastboot flashing unlock         # ★ データが全消去される
```

- 実行すると約 77 秒かかり、**タブレットの画面側で「音量アップ」キーを押して確認する操作が必要**でした。
- 実行後に `fastboot getvar unlocked` → `unlocked: yes`。
- `fastboot reboot` で再起動すると、初期設定画面になります。アンロックの警告画面が毎回出ます。
- 起動後は `ro.boot.flash.locked=0`、`verifiedbootstate=orange`、`vbmeta.device_state=unlocked`。

## 4. GSI の導入

### 4-1. GSI の選定

- 配布されている TrebleDroid の GSI は `ab` 系のみで、A-only 専用イメージはありません。この端末は system-as-root の動的パーティション構成なので、`arm64-ab-vanilla` を使いました（実際に起動しました）。
- カーネルが 4.19 なので、新しすぎる Android（14 以降）は避け、Android 13 の最終版 `ci-20230905` を選びました。
- 容量: 展開後 1,931,804,672 バイトで、ストックの `system`（`0x72E12000` = 1,927,356,416 バイト）より約 4.2 MiB 大きいため、`system` を拡張します（`super` は約 7.3 GB あるため、`product` を消さなくても収まります）。

```bash
curl -L -O https://github.com/TrebleDroid/treble_experimentations/releases/download/ci-20230905/system-td-arm64-ab-vanilla.img.xz
xz -t system-td-arm64-ab-vanilla.img.xz
xz -dk system-td-arm64-ab-vanilla.img.xz
```

### 4-2. `vbmeta` の準備（ここが重要）

メインの `vbmeta` だけを、**フラグ 1（`HASHTREE_DISABLED` のみ）** にします。AVB ヘッダーのフラグは、オフセット 120 のビッグエンディアン u32 です。

```python
import struct
d = bytearray(open('backup/vbmeta.bin', 'rb').read())
assert d[:4] == b'AVB0'
struct.pack_into('>I', d, 120, 1)      # 1 = HASHTREE_DISABLED のみ
open('vbmeta_flag1.bin', 'wb').write(bytes(d))
```

`vbmeta_system` と `vbmeta_vendor` は、**オリジナルのまま**にします。

書き込みは mtkclient でも fastboot でも可能です（fastbootd に入らなくても、Preloader 経由で直接書けます）。

```bash
./venv/bin/mtk w vbmeta vbmeta_flag1.bin
```

### 4-3. fastbootd に入って `system` を書き込む

動的パーティション（`super`）内の `system` へは、fastbootd から書き込みます。通常の `adb reboot fastboot` でも入れます（USB デバッグが有効なら）。

```bash
fastboot reboot fastboot
fastboot getvar is-userspace                         # yes
fastboot resize-logical-partition system 2147483648  # 2 GiB に拡張
fastboot flash system system-td-arm64-ab-vanilla.img
fastboot erase userdata
fastboot erase metadata
fastboot reboot
```

書き込みは 8 分割（sparse）で、約 1 分で終わりました。初回起動後、TrebleDroid のブートアニメーションを経て、Android 13 のデスクトップが表示されました。

## 5. 失敗と原因（今回のハマりどころ）

### 5-1. 症状

GSI 書き込み後、リカバリに落ちて "Can't load Android system. Your data may be corrupt..." と表示され、メニューは "Try again" と "Factory data reset" のみ。Factory data reset でも直りませんでした。

### 5-2. 切り分け

- 最初は、削除した `product` が原因（起動時の fstab で必須のため）と疑いました。`product` を作り直してストックの `product.img` を書き戻しましたが、直りませんでした。
- **ログの取り方:** リカバリでは `adb` が `unauthorized` で使えません。そこで、`cache` パーティション（ext4）を mtkclient で読み出し、`strings` で調べると、リカバリのログ（`last_log`）が入っていました。
  ```bash
  ./venv/bin/mtk r cache cache.bin
  strings -n 6 cache.bin | grep -E "Command: |reason"
  # Command: "/system/bin/recovery" "--prompt_and_wipe_data" "--reason=init_user0_failed"
  ```
  → Android は起動の途中まで進み、ユーザー 0 の初期化（`init_user0`）で失敗していました。カーネルパニックなどはありません。
- **ストックの `system` に戻しても同じ失敗** → GSI ではなく、`vbmeta` の設定が原因と判明しました。
- 3 つの `vbmeta` をバックアップのオリジナルに戻すと、ストックが起動しました。

### 5-3. 結論

| `vbmeta` の設定 | 結果 |
|---|---|
| オリジナル（検証有効） | ストックは起動 |
| 3 つとも `--disable-verity --disable-verification`（フラグ 3） | GSI でもストックでも **失敗**（`init_user0_failed`） |
| メインの `vbmeta` のみフラグ 1、他はオリジナル | ストック・GSI とも **起動** |

「検証無効」が原因と考えられますが、**TEE（keymaster）が検証状態に依存するためではないか**というのは推測で、未検証です。

## 6. 復旧の手順

### 6-1. fastboot / fastbootd に入れないとき（リカバリで固まった場合）

物理キーで fastboot に入れない場合は、**`misc` パーティションに「次回は fastbootd で起動」という指示（BCB）を書き込み**ます。これで、リカバリ経由で fastbootd に入れました。

```python
d = bytearray(open('backup/misc.bin', 'rb').read())
d[0:32]  = b'boot-recovery'.ljust(32, b'\0')   # command
d[32:64] = b'\0' * 32                          # status
d[64:832] = b'recovery\n--fastboot\n'.ljust(768, b'\0')   # recovery
open('misc_fastboot.bin', 'wb').write(bytes(d))
```

```bash
./venv/bin/mtk w misc misc_fastboot.bin   # 待機 → 電源オフの端末を USB 接続
# 書き込み後、電源ボタンで起動すると fastbootd に入る
```

再起動ループ中でも、毎回 Preloader の窓が開くので、`mtk` が捕まえられます。

### 6-2. ストックの OS に戻す

- `vbmeta`、`vbmeta_system`、`vbmeta_vendor` をバックアップのオリジナルに戻します。
- `system`（と必要なら `product`、`vendor`）を、バックアップの `super.bin` から取り出したイメージで書き戻します。
- または、`super.bin` 全体を書き戻します。

`super.bin` から論理パーティションを取り出す簡易スクリプト（LP メタデータのヘッダーは 128 バイト、v10.0）:

```python
# lp_extract.py <super.bin> <outdir> <partition>...
import struct, sys, os
super_path, outdir, want = sys.argv[1], sys.argv[2], sys.argv[3:]
f = open(super_path, 'rb')
f.seek(0x1000); geo = f.read(52)
assert struct.unpack('<I', geo[:4])[0] == 0x616c4467
f.seek(0x3000); h = f.read(256)
assert struct.unpack('<I', h[:4])[0] == 0x414c5030
f.seek(0x3000 + struct.unpack('<I', h[8:12])[0])      # header_size
tables_size, = struct.unpack('<I', h[44:48])
poff, pnum, psz = struct.unpack('<III', h[80:92])
eoff, enum, esz = struct.unpack('<III', h[92:104])
tables = f.read(tables_size)
parts = {}
for i in range(pnum):
    e = tables[poff + i*psz: poff + (i+1)*psz]
    name = e[:36].split(b'\0')[0].decode()
    _, first, num, _ = struct.unpack('<IIII', e[36:52])
    parts[name] = (first, num)
os.makedirs(outdir, exist_ok=True)
for name in want:
    first, num = parts[name]
    with open(os.path.join(outdir, name + '.img'), 'wb') as o:
        for j in range(first, first + num):
            e = tables[eoff + j*esz: eoff + (j+1)*esz]
            nsec, ttype, tdata = struct.unpack('<QIQ', e[:20])
            assert ttype == 0
            f.seek(tdata * 512); left = nsec * 512
            while left:
                b = f.read(min(left, 1 << 24)); o.write(b); left -= len(b)
```

## 7. Google アプリの追加（Play ストア、YouTube、Gmail、マップ）

### 7.1 なぜイメージの加工が必要か

- TrebleDroid の `vanilla` GSI には、Google Mobile Services（GMS）が入っていません。
- Google 公式の GMS 入り GSI もありますが、ライセンスはアプリの互換性テスト用に限られていて、改変・再配布が禁止されているため、日常使いには使いませんでした。
- 一般的な「リカバリで GApps の zip を焼く」方法は使えません。この端末には TWRP がなく、`system` は `super`（動的パーティション）の中にあります。
- そのため、PC 上で GSI の `system` イメージに、GApps をオフラインで組み込みました。

### 7.2 入手元と検証

**MindTheGapps 13.0.0 arm64** の `20231025_200931` を使いました。公式の GitLab プロジェクト（`gitlab.com/MindTheGapps/vendor_gapps`）が案内している、GitHub の組織のリリースです。公開者は LineageOS の開発者です。

```bash
B=https://github.com/MindTheGapps/13.0.0-arm64/releases/download/MindTheGapps-13.0.0-arm64-20231025_200931
curl -L -O $B/MindTheGapps-13.0.0-arm64-20231025_200931.zip
curl -L -O $B/release.x509.pem
sha256sum MindTheGapps-13.0.0-arm64-20231025_200931.zip
# 3ff2edaa75406eb4214402fca6906d4b413ab50afdb1af033d9e396992338d0b  （私が取得したもの）
unzip -tq MindTheGapps-*.zip
# zip の署名者と公開されている証明書の比較（同じ公開元なので、独立した検証ではなく、整合性の確認）
unzip -p MindTheGapps-*.zip META-INF/CERT.RSA | openssl pkcs7 -inform DER -print_certs | openssl x509 -noout -fingerprint -sha256
openssl x509 -in release.x509.pem -noout -fingerprint -sha256
# どちらも: 91:37:0E:89:7E:35:BD:90:A2:62:B7:3E:82:96:66:18:19:C1:3D:54:67:FD:30:A1:0D:F8:48:DE:14:F5:67:76
```

zip の中身は、基本の Google アプリだけです（Play 開発者サービスの `GmsCore`、Play ストアの `Phonesky`、サービスフレームワーク、セットアップウィザード、Google アプリの `Velvet`、同期アダプターなど）。YouTube、Gmail、マップ、Chrome は、あとから Play ストアで入れます。

> zip には、リカバリ向けのシェルスクリプト（`META-INF/com/google/android/update-binary`）が入っています。**これは実行していません。** 中身を読み（ファイルのコピーとパーミッション設定だけ）、同じ処理を自分で再現しました。

### 7.3 ファイルを置く場所

この GSI では、`/product` は `/system/product` への、`/system_ext` は `/system/system_ext` へのシンボリックリンクです。ストックの `product` パーティションは**マウントされていません**。そのため、zip の `system/product/...` と `system/system_ext/...` は、そのまま GSI の `system` イメージに入れれば有効になります（`adb shell ls -l /product` と `adb shell mount` で確認できます）。

### 7.4 イメージの作成

インストーラーの処理と、再現した内容は、次のとおりです。

- ディレクトリは `0755 root:root`、ファイルは `0644 root:root`（`*.sh` と拡張子なしは `0755`）
- 追加したものすべてに、SELinux ラベル `u:object_r:system_file:s0`（末尾に NUL を付けた `security.selinux`）
- `SetupWizard` を入れる場合は、`system_ext/priv-app/Provision` を削除
- `VelvetTitan`（379MB、tangorpro という機種専用）は除外

障害が2つありました。

1. GSI のイメージは、ext4 の **`shared_blocks`** 機能付き（重複排除された読み取り専用）で、そのままでは書き込めません。先に拡張して、「unshare」する必要があります。
2. 3GiB に拡張しても、空きは約730MBです。`VelvetTitan` と `addon.d` を除いたペイロードは、約544MBです。

```bash
cp system-td-arm64-ab-vanilla.img system_gapps.img
truncate -s 3G system_gapps.img
e2fsck -fn system_gapps.img                       # クリーンであること
resize2fs system_gapps.img                        # ファイルシステムを 3 GiB に拡張
e2fsck -fy -E unshare_blocks system_gapps.img     # shared_blocks を解除

mkdir payload && unzip -q -d payload MindTheGapps-*.zip 'system/*'
rm -rf payload/system/product/priv-app/VelvetTitan payload/system/addon.d

# debugfs のみ使用（マウントも sudo も不要）
python3 scripts/embed_gapps.py system_gapps.img payload/system
e2fsck -fn system_gapps.img                       # 引き続きクリーンであること
```

行った確認は、次のとおりです。`e2fsck` はクリーン。`Phonesky.apk`、`GmsCore.apk`、`GoogleServicesFramework.apk`、`google.xml`、`libjni_latinimegoogle.so` を `debugfs` で取り出して、zip の中身と一致することを確認。ラベルとパーミッションは上記のとおり。`Provision` は削除済み。既存のディレクトリ（例: `system_lib_file` の `product/lib64`）は、変更なし。

### 7.5 書き込み

```bash
adb reboot fastboot
fastboot resize-logical-partition system 3221225472   # 3 GiB。ストックの product/vendor はそのまま（合計約5.9GBで、7.3GBの super に収まる）
fastboot flash system system_gapps.img
fastboot erase userdata
fastboot erase metadata
fastboot reboot
```

この初回起動では、データを初期化します。Google の既定の実行時権限（`default-permissions-*.xml`）は、クリーンな初回起動で付与されます。ビルドのフィンガープリントは、今回変わらないためです。

### 7.6 結果

Google のセットアップウィザードが表示され、ログインでき、Play ストア経由で Play 開発者サービスが更新され、YouTube、Gmail、マップ、Chrome がインストールできて、動きました。「端末が認定されていません」という警告は、見ませんでした。未確認: Play Integrity に依存するアプリ（銀行・決済）、DRM 動画。

起動しない場合は、4 章の素の GSI を書き込み直してください（4.2 の `vbmeta` の設定は、そのまま維持します）。

## 8. パーティション構成（`printgpt`）

`recovery`、`misc`、`para`、`expdb`、`frp`、`vbmeta`、`vbmeta_system`、`vbmeta_vendor`、`md_udc`、`metadata`、`nvcfg`、`nvdata`、`persist`、`protect1/2`、`seccfg`、`sec1`、`proinfo`、`boot_para`、`nvram`、`logo`、`md1img`、`spmfw`、`scp1/2`、`sspm_1/2`、`gz1/2`、`lk`、`lk2`、`boot`、`vendor_boot`、`dtbo`、`tee1/2`、`super`（`0x2c000000` から 7.3 GB）、`cache`、`userdata`、`otp`、`flashinfo`。

`super` 内の論理パーティションは `system`、`vendor`、`product` の 3 つで、ストックのサイズは `system` = `0x72E12000`、`vendor` = `0x1E56F000`、`product` = `0x8182F000` でした。

## 9. その他のメモ

- 検索した範囲では、Tab 13 向けのカスタム ROM（LineageOS など）や TWRP の情報は見つかりませんでした。
- 調査時の参考になった情報源: Hovatek フォーラムの Blackview 各機種のスレッド、mtkclient の README、TrebleDroid（phhusson）のリリース、Android 公式の GSI 解説。
- ブートローダーを再ロックする場合の手順は、試していないため、本メモには含めていません。

## 10. 未確認・今後の課題

- GPS が安定して動いていなさそう（未調査: GNSS の HAL / ベンダーのバイナリと GSI の相性、位置情報の設定）。
- 指紋・顔認証、SIM／モバイル通信（4G）、USB OTG、スリープ復帰、待機中の消費電力。
- アンロック状態の GSI での、銀行・決済アプリと DRM 動画。
- OTA 更新はありません。更新するには、イメージを作り直して、7 章を繰り返します。
- Magisk などによるルート化（`boot.img` へのパッチ）。
- `vbmeta` のフラグ 1 がなぜ通るかの裏付け（推測のみ）。
- 他の GSI（crDroid など）や、Android 14 以降の GSI の動作。
