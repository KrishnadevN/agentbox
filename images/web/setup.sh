#!/usr/bin/env bash
npm install -g pnpm
npx -y playwright@latest install-deps chromium
rm -rf /var/lib/apt/lists/* /root/.npm
