# jellyfin

Jellyfin メディアサーバーを LiRu 上の Podman Quadlet で運用する。メディアは USB 接続の外付け SSD に置き、Tailscale サイドカー経由で `https://jellyfin.<tailnet>` として Tailnet 内に公開する。

> このサービスは LiRu（Manjaro、USB SSD 接続）専用。`deploy-all` には含まれない。

## 前提条件

- LiRu に外付け SSD（Samsung SSD 860 EVO 500GB、ext4、UUID `f11bec43-bd87-4333-a1f2-406af37eabb3`）が接続されている
- `loginctl enable-linger` 設定済み
- Tailscale admin console で `jellyfin` 用の authkey を発行済み（OCI の sidecar と同じく `tag:infra` を付ける）

## 構成

| ファイル                              | 役割                                          |
| ------------------------------------- | --------------------------------------------- |
| `justfile`                            | 操作コマンド定義                              |
| `secrets.yaml`                        | Tailscale authkey（sops + age で暗号化）      |
| `quadlet/jellyfin.container`          | Jellyfin コンテナ（Intel iGPU を渡す）        |
| `quadlet/jellyfin-ts.container.tmpl`  | Tailscale サイドカーテンプレート              |
| `quadlet/jellyfin-ts-serve.json.tmpl` | Tailscale Serve 設定（:443 → 127.0.0.1:8096） |
| `quadlet/jellyfin-config.volume`      | Jellyfin 設定・メタデータ（ルートディスク）   |
| `quadlet/jellyfin-ts-state.volume`    | Tailscale state                               |

## ストレージ

SSD は fstab で `/srv/media` にマウントする（`nofail` 付き。SSD が抜けていても起動は止まらない）。

| ホスト側                    | コンテナ側     | 用途                           |
| --------------------------- | -------------- | ------------------------------ |
| `/srv/media/music`          | `/media/music` | 音楽（読み取り専用）           |
| `/srv/media/movie`          | `/media/movie` | 映画（読み取り専用）           |
| `/srv/media/jellyfin-cache` | `/cache`       | トランスコード・画像キャッシュ |

music と movie 以外のライブラリはリポジトリに含めない。ホスト側で `~/.config/containers/systemd/jellyfin.container.d/local.conf` に `[Container]` と `Volume=` を書いて追加する。`deploy` はこのディレクトリに触れない。

ルートディスクの空きが少ない（2026-11-26 時点で 24G）ため、キャッシュは SSD に置く。

`jellyfin.container` は `ExecStartPre=mountpoint -q /srv/media` で SSD のマウントを確認してから起動する。SSD なしで起動すると空のディレクトリをスキャンし、ライブラリの登録が消えるため。SSD がないあいだは 30 秒おきに起動を再試行し、SSD を挿し直せば自動で起動する。

## セットアップ

```bash
nix develop
just jellyfin setup-disk          # fstab 追記・マウント・ディレクトリ作成（sudo を使う。再実行しても同じ結果）
sops services/jellyfin/secrets.yaml   # ts_authkey を記入
just jellyfin deploy
just jellyfin start
```

`setup-disk` は SSD を ext4 のまま使い、フォーマットしない。既存のファイルは残る。

初回アクセス時のウィザードで、ライブラリを次のように登録する。

| ライブラリ | コンテンツの種類 | フォルダー     |
| ---------- | ---------------- | -------------- |
| Music      | 音楽             | `/media/music` |
| Movies     | 映画             | `/media/movie` |

ハードウェアトランスコードは、管理画面の「再生 → トランスコード」で Intel QuickSync（QSV）を選ぶと有効になる。

## コマンド

| コマンド                    | 説明                                         |
| --------------------------- | -------------------------------------------- |
| `just jellyfin setup-disk`  | SSD のマウントとディレクトリ作成（sudo）     |
| `just jellyfin deploy`      | Quadlet ファイルインストール + daemon-reload |
| `just jellyfin start`       | サービス起動                                 |
| `just jellyfin stop`        | サービス停止                                 |
| `just jellyfin restart`     | サービス再起動                               |
| `just jellyfin status`      | サービス状態確認                             |
| `just jellyfin logs`        | ログ表示                                     |
| `just jellyfin logs-follow` | ログフォロー                                 |
| `just jellyfin update`      | コンテナイメージ更新                         |
