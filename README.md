


### Create the rules to allow port communication of WSL with the local site

New-NetFirewallRule -DisplayName "Allow WSL to LocalWP" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 `
  -RemoteAddress 172.18.128.0/20


```New-NetFirewallRule -DisplayName "Allow WSL to LocalWP HTTPS" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 `
  -RemoteAddress 172.18.128.0/20```
### Delete these rules later for the local site
```Remove-NetFirewallRule -DisplayName "Allow WSL to LocalWP"
Remove-NetFirewallRule -DisplayName "Allow WSL to LocalWP HTTPS"```