#!/bin/bash

# 1. Find the currently active Wi-Fi connection profile name
CONNECTION_NAME=$(nmcli -t -f NAME,TYPE connection show --active | grep "802-11-wireless" | cut -d: -f1)

# Check if an active Wi-Fi connection was actually found
if [ -z "$CONNECTION_NAME" ]; then
    echo "Error: No active Wi-Fi connection found."
    exit 1
fi

echo "Found active Wi-Fi connection: $CONNECTION_NAME"
echo "Configuring DNS to Cloudflare (1.1.1.1)..."

# 2. Set Cloudflare DNS for IPv4 and ignore the ISP's default DNS
nmcli connection modify "$CONNECTION_NAME" ipv4.dns "1.1.1.1 1.0.0.1"
nmcli connection modify "$CONNECTION_NAME" ipv4.ignore-auto-dns yes

# 3. Set Cloudflare DNS for IPv6 (prevents ISP DNS leaks via IPv6)
nmcli connection modify "$CONNECTION_NAME" ipv6.dns "2606:4700:4700::1111 2606:4700:4700::1001"
nmcli connection modify "$CONNECTION_NAME" ipv6.ignore-auto-dns yes

# 4. Restart the connection to apply the changes
echo "Restarting Wi-Fi connection..."
nmcli connection down "$CONNECTION_NAME"
nmcli connection up "$CONNECTION_NAME"

# 5. Flush the local DNS cache (if systemd-resolved is running)
if systemctl is-active --quiet systemd-resolved; then
    resolvectl flush-caches
    echo "DNS cache flushed."
fi

echo "Success! You are now using Cloudflare DNS."
