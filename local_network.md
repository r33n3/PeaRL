# Home Network Access Setup

Docker Desktop on Windows only binds container ports to the Windows loopback (`127.0.0.1`).
To expose PeaRL services to other devices on the home network, run the following in an
**Administrator PowerShell** on Windows (not WSL).

## Active Port Proxy Rules

The following `netsh` portproxy rules are currently configured on this machine:

| LAN Port | Forwards To | Service |
|----------|-------------|---------|
| 8080 | WSL (192.168.27.222):8080 | PeaRL API |
| 8082 | WSL (192.168.27.222):8082 | Reserved |
| 5177 | localhost:5177 | PeaRL Frontend |
| 8001 | localhost:8001 | Reserved |

> **Note:** 8082 and 8001 are configured in portproxy but not yet assigned to a service in docker-compose.

## To Recreate Rules (if lost)

Run in **Administrator PowerShell**, replacing `<WSL_IP>` with the current WSL IP
(find it with `wsl hostname -I` from PowerShell):

```powershell
# API — forwards to WSL
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=<WSL_IP>
netsh interface portproxy add v4tov4 listenport=8082 listenaddress=0.0.0.0 connectport=8082 connectaddress=<WSL_IP>

# Frontend — forwards to Windows localhost
netsh interface portproxy add v4tov4 listenport=5177 listenaddress=0.0.0.0 connectport=5177 connectaddress=127.0.0.1
netsh interface portproxy add v4tov4 listenport=8001 listenaddress=0.0.0.0 connectport=8001 connectaddress=127.0.0.1
```

## Windows Firewall Rules

```powershell
netsh advfirewall firewall add rule name="PeaRL API" dir=in action=allow protocol=TCP localport=8080
netsh advfirewall firewall add rule name="PeaRL API Alt" dir=in action=allow protocol=TCP localport=8082
netsh advfirewall firewall add rule name="PeaRL Frontend" dir=in action=allow protocol=TCP localport=5177
netsh advfirewall firewall add rule name="PeaRL Reserved" dir=in action=allow protocol=TCP localport=8001
```

## After Starting `docker compose up`

Other devices on the home network can access:

| Service  | URL |
|----------|-----|
| Frontend | http://192.168.1.2:5177 |
| API      | http://192.168.1.2:8080/api/v1/health |

## WSL IP Note

The WSL IP (e.g. `192.168.27.222`) changes on WSL restarts. If the portproxy stops working,
update the `connectaddress` for the 8080/8082 rules with the new WSL IP:

```powershell
netsh interface portproxy delete v4tov4 listenport=8080 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=<NEW_WSL_IP>
```

## To Remove All Rules

```powershell
netsh interface portproxy delete v4tov4 listenport=8080 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=8082 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=5177 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=8001 listenaddress=0.0.0.0
netsh advfirewall firewall delete rule name="PeaRL API"
netsh advfirewall firewall delete rule name="PeaRL API Alt"
netsh advfirewall firewall delete rule name="PeaRL Frontend"
netsh advfirewall firewall delete rule name="PeaRL Reserved"
```
