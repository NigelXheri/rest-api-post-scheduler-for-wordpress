


### Create the rules to allow port communication of WSL with the local site

New-NetFirewallRule -DisplayName "Allow WSL to LocalWP" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 `
  -RemoteAddress 172.18.128.0/20


```New-NetFirewallRule -DisplayName "Allow WSL to LocalWP HTTPS" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 `
  -RemoteAddress 172.18.128.0/20```
### Delete these rules later for the local site
```Remove-NetFirewallRule -DisplayName "Allow WSL to LocalWP" `
Remove-NetFirewallRule -DisplayName "Allow WSL to LocalWP HTTPS"```

### TODOS
- [] Next time, you will need to find the video from the scheduled videos from the YouTube API by searching the date in the title (for example: "4 tetor") and then use the YouTube video title for the final post title. That is so that the capitalization of the Title is correct because the PDF doesn't contain that information. 
- [] Also, the block tags should be added to the content so that it doens't need to later be converted.
- [] Handle photo search, upload and compression 
- [] Make it check for existing schedulings and only schedule posts that have their videos already uploaded, starting from next day's date