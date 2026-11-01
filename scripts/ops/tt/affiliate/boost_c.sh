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
echo "### boost C rc=$rc $(date -u '+%d.%m %H:%M UTC')"
if [ "$rc" -ne 3 ]; then
  echo "### linkshare big (cap 40) $(date -u '+%d.%m %H:%M UTC')"
  docker compose exec -T worker python -I - --big-only --cap 40 --need-reset < /root/tt-ops/aff_linkshare.py 2>&1 | grep -E 'quota|saved big|to send|CREATE|READBACK|test account|ERR|DONE'
  echo "### linkshare rc=${PIPESTATUS[0]}"
fi
echo "### END $(date -u '+%d.%m %H:%M UTC')"
