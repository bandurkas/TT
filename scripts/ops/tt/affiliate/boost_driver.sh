#!/bin/bash
cd /root/TT
run() {
  echo "### $1: $2"
  docker compose exec -T worker python -I - --create --tag "$1" --users "$2" < /tmp/aff_boost.py 2>&1 | grep -E 'to send|CREATE|READBACK|ERR|DONE|quota'
  return ${PIPESTATUS[0]}
}
REAL_SMALL="za.zara_,sideeru,aireenarelia2025,farhan_marup328,prefxerred,boyan392,puspaindah9,ejey.12,chillakiya,shinohanaandreas,dannidaan_,pietersite_t"
REAL_BIG="wakkancillkoslett,mediatama.team,flip_id,ootdbarubar,_langvzxx,diqiaff1"
if ! run "Sell A" "$REAL_SMALL,$REAL_BIG"; then
  run "Sell A1" "$REAL_SMALL" || { run "Sell A1a" "za.zara_,sideeru,aireenarelia2025,farhan_marup328,prefxerred,boyan392"; run "Sell A1b" "puspaindah9,ejey.12,chillakiya,shinohanaandreas,dannidaan_,pietersite_t"; }
  run "Sell A2" "$REAL_BIG" || { run "Sell A2a" "wakkancillkoslett,mediatama.team,flip_id"; run "Sell A2b" "ootdbarubar,_langvzxx,diqiaff1"; }
fi
run "Sell B" "iflyad_45_id,rampuyxohrl,shopbackid_" || { run "Sell B1" "rampuyxohrl"; run "Sell B2" "shopbackid_"; run "Sell B3" "iflyad_45_id"; }
echo "### END"
