# samba

LiRu の `/srv/media`（USB SSD）を SMB で共有する。Windows のエクスプローラーから `\\samba\media` を開き、ドラッグでファイルをコピーできるようにするため。Tailscale sidecar 経由で Tailnet 内だけに公開する。

> このサービスは LiRu 専用。`deploy-all` には含まれない。SSD のマウントは [jellyfin](../jellyfin/README.md) の `setup-disk` で行う。

## 構成

| ファイル                          | 役割                                                           |
| --------------------------------- | -------------------------------------------------------------- |
| `justfile`                        | 操作コマンド定義                                               |
| `secrets.yaml`                    | Tailscale authkey と SMB のユーザー・パスワード（sops 暗号化） |
| `quadlet/samba.container.tmpl`    | Samba コンテナ（`dockurr/samba`）                              |
| `quadlet/smb.conf`                | Samba 設定。共有名 `media` で `/srv/media` を読み書き可で公開  |
| `quadlet/samba-ts.container.tmpl` | Tailscale サイドカーテンプレート                               |
| `quadlet/samba-ts-serve.json`     | Tailscale Serve 設定（TCP 445 → 127.0.0.1:445）                |
| `quadlet/samba-ts-state.volume`   | Tailscale state                                                |

## 設計メモ

- `smb.conf` の `force user = root` で、SMB 経由の読み書きをすべてコンテナの root として行う。rootless podman ではコンテナの root がホストの noize に対応するため、書き込んだファイルの所有者は noize になる。イメージ既定の UID 1000 で書くと、ホスト側では subuid（100999 など）の所有になる
- SSD が未マウントのときは起動しない（`ExecStartPre=mountpoint -q /srv/media`）。マウントポイントの下に書き込むと、ルートディスクに溜まるため
- Jellyfin には `/srv/media` を読み取り専用で渡しているので、SMB 側の変更は Jellyfin のスキャンで反映される
- Tailscale sidecar は userspace networking で動くため、転送速度は LAN 直結の SMB より遅くなる

## セットアップ

1. Tailscale admin console で authkey を発行する（`tag:infra`、再利用可）
2. `secrets.yaml` の `ts_authkey` に記入する。SMB のパスワードは生成済み

```bash
nix develop
sops services/samba/secrets.yaml   # ts_authkey を記入
just samba deploy
just samba start
just samba credentials             # ユーザー名とパスワードを表示
```

Windows ではエクスプローラーのアドレス欄に `\\samba\media` を入力し、`credentials` のユーザー名とパスワードでログインする。ドライブとして割り当てる場合は「ネットワーク ドライブの割り当て」で同じパスを指定する。

## コマンド

| コマンド                 | 説明                                         |
| ------------------------ | -------------------------------------------- |
| `just samba deploy`      | Quadlet ファイルインストール + daemon-reload |
| `just samba start`       | サービス起動                                 |
| `just samba stop`        | サービス停止                                 |
| `just samba restart`     | サービス再起動                               |
| `just samba status`      | サービス状態確認                             |
| `just samba logs`        | ログ表示                                     |
| `just samba logs-follow` | ログフォロー                                 |
| `just samba credentials` | SMB のユーザー名とパスワードを表示           |
| `just samba update`      | コンテナイメージ更新                         |
