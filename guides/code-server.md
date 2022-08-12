# Setting up dev environment

first we will set up lets-encrypt to use cloudflare dns verification so we can obtain wildcard certs:

```console
ubuntu@localhost:~$ sudo snap install core
ubuntu@localhost:~$ sudo snap refresh core
ubuntu@localhost:~$ sudo snap install --classic certbot
ubuntu@localhost:~$ sudo snap set certbot trust-plugin-with-root=ok
ubuntu@localhost:~$ sudo snap install certbot-dns-cloudflare
```

then we need to add the cloudflare api token to the following config file:

```console
ubuntu@localhost:~$ sudo mkdir -p /root/.secrets
ubuntu@localhost:~$ sudo touch /root/.secrets/cloudflare.ini
ubuntu@localhost:~$ sudo chmod 0700 /root/.secrets/
ubuntu@localhost:~$ sudo chmod 0400 /root/.secrets/cloudflare.ini
ubuntu@localhost:~$ sudo nano /root/.secrets/cloudflare.ini
```

the file should contain the following line (where xxxx is an api-token):

```text
dns_cloudflare_api_token = xxxx
```

Now we obtain a new certificate:

```console
ubuntu@localhost:~$ sudo certbot certonly \
    --dns-cloudflare \
 --dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
 -d plasmacan-dev.com,*.plasmacan-dev.com \
 --preferred-challenges dns-01
```

we can view the renewal timer like so:

```console
ubuntu@localhost:~$ sudo systemctl status snap.certbot.renew.timer
```

When the cert renews, we want nginx to reload, so we need to create the script to do so:

```console
ubuntu@localhost:~$ sudo touch /etc/letsencrypt/renewal-hooks/deploy/nginx_reload.sh
ubuntu@localhost:~$ sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/nginx_reload.sh
ubuntu@localhost:~$ sudo nano /etc/letsencrypt/renewal-hooks/deploy/nginx_reload.sh
```

The script contains the following:

```text
#!/bin/bash
systemctl reload nginx
```

To pass through IP geographic data to the webapp, we need to install and configure geoipupdate:

```console
ubuntu@localhost:~$ sudo apt-get install geoipupdate
ubuntu@localhost:~$ sudo nano /etc/GeoIP.conf
```

The config file should contain the following: (AccountID and LicenseKey are obtained from
<https://www.maxmind.com/en/my_license_key>)

```text
EditionIDs GeoLite2-Country
AccountID xxxx
LicenseKey xxxx
```

To confirm all is well, we will attempt a geoip database update like so:

```console
ubuntu@localhost:~$ sudo geoipupdate -v
```

Assuming there are no errors, we will now schedule the update to run automatically:

```console
ubuntu@localhost:~$ sudo crontab -e
```

add the following to the crontab:

```text
# Run GeoIP database update every Tuesday at 02:00
0 2 * * 2 /usr/bin/geoipupdate
```

The dev environment is going to run inside a different (non-privileged) user account which we need to create:

```console
ubuntu@localhost:~$ sudo useradd -s /bin/bash -m -d /home/plasma -g www-data plasma
```

We will now set up the code-server to run as that user:

```console
ubuntu@localhost:~$ curl -fsSL https://code-server.dev/install.sh | sh -s -- --dry-run
ubuntu@localhost:~$ curl -fsSL https://code-server.dev/install.sh | sh
ubuntu@localhost:~$ sudo systemctl enable --now code-server@plasma
ubuntu@localhost:~$ sudo cat /home/plasma/.config/code-server/config.yaml
```

We will now install some plugins and remove some others inside of code-server:

```console
ubuntu@localhost:~$ sudo -u plasma code-server \
 --install-extension ms-python.python \
 --install-extension streetsidesoftware.code-spell-checker \
 --install-extension EditorConfig.EditorConfig \
 --install-extension esbenp.prettier-vscode \
 --install-extension dbaeumer.vscode-eslint \
 --install-extension stylelint.vscode-stylelint \
 --install-extension DavidAnson.vscode-markdownlint \
 --install-extension alefragnani.Bookmarks

ubuntu@localhost:~$ sudo -u plasma code-server --uninstall-extension ms-toolsai.jupyter
```

code-server is running now but will need to be put behind the proxy, which we need to install:

```console
ubuntu@localhost:~$ sudo apt-get install nginx libnginx-mod-http-headers-more-filter
```

we can delete the default nginx config and make a new one:

```console
ubuntu@localhost:~$ sudo rm /etc/nginx/sites-enabled/default
ubuntu@localhost:~$ sudo nano /etc/nginx/sites-available/plasmacan-dev.com
```

the config should look like this:

```text
geoip2 /var/lib/GeoIP/GeoLite2-Country.mmdb {
    auto_reload 1h;
    $geoip2_data_country_code default=XX source=$remote_addr country iso_code;
}

proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=myzone0:10m inactive=24h max_size=1g;

server {
    listen 80 default_server;
    listen 443 ssl;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header CF-IPCountry $geoip2_data_country_code;
        proxy_set_header CF-Connecting-IP $remote_addr;
        proxy_set_header CF-Visitor "{\"scheme\":\"$scheme\"}";
        proxy_set_header CF-Ray $request_id-XXX;
        more_set_headers 'Server: Plasma';
        add_header CF-Cache-Status $upstream_cache_status;
        add_header CF-Ray $request_id-XXX;
        proxy_set_header X-Request-ID "";
        proxy_buffering        on;
        proxy_cache            myzone0;
    }

    ssl_certificate /etc/letsencrypt/live/plasmacan-dev.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/plasmacan-dev.com/privkey.pem;
}

server {
    listen 80;
    listen 443 ssl;
    server_name code.plasmacan-dev.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection upgrade;
        proxy_read_timeout 8h;
        proxy_set_header Accept-Encoding gzip;
    }

    ssl_certificate /etc/letsencrypt/live/plasmacan-dev.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/plasmacan-dev.com/privkey.pem;
}
```

and then we make a symlink for the config:

```console
ubuntu@localhost:~$ sudo ln -s /etc/nginx/sites-available/plasmacan-dev.com /etc/nginx/sites-enabled/
```

We also need to make the cache directory for the proxy:

```console
ubuntu@localhost:~$ sudo mkdir /var/cache/nginx
ubuntu@localhost:~$ sudo chown www-data:www-data /var/cache/nginx
```

Now the config can be tested and nginx restarted:

```console
ubuntu@localhost:~$ sudo nginx -t
ubuntu@localhost:~$ sudo systemctl restart nginx
ubuntu@localhost:~$ sudo systemctl status nginx
```

Install the development global system dependencies:

```console
ubuntu@localhost:~$ sudo apt-get install python3-pip openjdk-11-jre
ubuntu@localhost:~$ sudo snap install node --channel=14/stable --classic
```

install the global linting/formatting tools

```console
ubuntu@localhost:~$ sudo npm install --global \
    eslint@8.15.0 \
    prettier@2.7.1 \
    stylelint@14.9.1 \
    markdownlint-cli@0.32.1
```

Clone/set up this repo:

```console
ubuntu@localhost:~$ sudo git clone https://github.com/plasmacan/core.git /opt/plasmacore
ubuntu@localhost:~$ cd /opt/plasmacore
ubuntu@localhost:~$ sudo chown plasma:www-data -R *
ubuntu@localhost:~$ sudo chown plasma:www-data -R .
ubuntu@localhost:~$ sudo find . -type d -exec chmod 2775 {} \;
ubuntu@localhost:~$ sudo find . -type f -exec chmod 664 {} \;
ubuntu@localhost:~$ sudo -u plasma pip install -r requirements.txt
ubuntu@localhost:~$ sudo -u plasma bash -l -c 'pre-commit install'
```

install the local linting/formatting tools (these are installed into the directory /opt/plasmacore)

```console
ubuntu@localhost:~$ sudo -u plasma npm install --local \
    eslint-config-prettier@8.5.0 \
    eslint-plugin-no-unsanitized@4.0.1 \
    stylelint-config-standard@25.0.0 \
    stylelint-config-prettier@9.0.3
```

Now we need to add the python scripts directory to the plasma user's PATH variable

```console
ubuntu@localhost:~$ echo 'export PATH="/home/plasma/.local/bin:$PATH"' | sudo -u plasma tee -a /home/plasma/.bashrc
```
