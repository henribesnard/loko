# Deploiement Loko

## Infos serveur

- **URL** : https://loko.wezon.fr
- **VPS** : `38.143.19.38` (Ubuntu 24.04)
- **Repertoire** : `/opt/loko/`
- **Container** : `loko-loko-1` (port 8001 -> 8000)
- **Reverse proxy** : Caddy (TLS auto Let's Encrypt)
- **DNS** : Cloudflare, enregistrement A `loko` -> `38.143.19.38` (proxied)
- **Admin token** : variable `loko_Admin_token` dans `.env` local

## Architecture

```
Navigateur
  -> Cloudflare (DNS + proxy + TLS client)
    -> Caddy (VPS :443, TLS origin, reverse proxy)
      -> Docker loko (localhost:8001 -> :8000)
        -> Uvicorn / FastAPI
```

## Mise a jour

```bash
ssh root@38.143.19.38
cd /opt/loko
git pull origin main
docker compose up -d --build
```

Verification :

```bash
docker ps --filter name=loko
curl http://localhost:8001/health
```

## Commandes utiles

```bash
# Logs applicatifs
docker logs loko-loko-1 --tail 100 -f

# Logs Caddy
tail -f /var/log/caddy/loko.log

# Redemarrer le container
cd /opt/loko && docker compose restart

# Redemarrer Caddy (apres modif Caddyfile)
systemctl reload caddy

# Arreter Loko
cd /opt/loko && docker compose down

# Arreter + supprimer les donnees
cd /opt/loko && docker compose down -v
```

## Configuration VPS

Le fichier `/opt/loko/.env` sur le VPS contient :

```env
LOKO_ADMIN_TOKEN=<valeur de loko_Admin_token du .env local>
LOKO_CORS_ORIGINS=https://loko.wezon.fr
```

Pour modifier le token : mettre a jour les deux `.env` (local et VPS) puis `docker compose up -d`.

## Rollback

```bash
cd /opt/loko
git log --oneline -5
git checkout <commit>
docker compose up -d --build
```

## Caddy

Bloc dans `/etc/caddy/Caddyfile` :

```caddyfile
loko.wezon.fr {
    log {
        output file /var/log/caddy/loko.log
    }
    reverse_proxy localhost:8001 {
        header_up Host {host}
        header_up X-Real-IP {remote}
    }
}
```
