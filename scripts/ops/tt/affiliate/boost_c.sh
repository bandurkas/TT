#!/bin/bash
# wave C: level 7-8 sellers at 15 %, waits for the weekly outreach quota reset (expected Sun ~13:00 Jakarta = 06:00 UTC)
cd /root/TT
now=$(date +%s); t=$(date -d '06:05' +%s)
[ "$t" -gt "$now" ] && sleep $((t - now))
rc=3
for i in $(seq 1 35); do
  echo "### try $i $(date -u '+%d.%m %H:%M UTC')"
  docker compose exec -T worker python -I - --create --only-big --need-reset --tag "Sell C" < /root/tt-ops/aff_boost.py 2>&1 | grep -E 'to send|CREATE|READBACK|ERR|DONE|quota|exit 3'
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 3 ] && break
  sleep 1800
done
echo "### END rc=$rc $(date -u '+%d.%m %H:%M UTC')"
