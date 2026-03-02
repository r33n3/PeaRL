# Home Network Access Setup

Docker Desktop on Windows only binds container ports to the Windows loopback (`127.0.0.1`).
To expose PeaRL services to other devices on the home network, run the following in an
**Administrator PowerShell** on Windows (not WSL).

## Port Proxy Rules

Forward LAN traffic through Docker Desktop's localhost binding:

```powershell
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=127.0.0.1
netsh interface portproxy add v4tov4 listenport=5174 listenaddress=0.0.0.0 connectport=5174 connectaddress=127.0.0.1
```

## Windows Firewall Rules

Allow inbound connections on the exposed ports:

```powershell
netsh advfirewall firewall add rule name="PeaRL API" dir=in action=allow protocol=TCP localport=8080
netsh advfirewall firewall add rule name="PeaRL Frontend" dir=in action=allow protocol=TCP localport=5174
```

## After Running

Other devices on the home network (192.168.1.x) can access:

| Service  | URL                                      |
|----------|------------------------------------------|
| Frontend | http://192.168.1.2:5174                  |
| API      | http://192.168.1.2:8080/api/v1/health    |

## To Remove Later

```powershell
netsh interface portproxy delete v4tov4 listenport=8080 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=5174 listenaddress=0.0.0.0
netsh advfirewall firewall delete rule name="PeaRL API"
netsh advfirewall firewall delete rule name="PeaRL Frontend"
```
