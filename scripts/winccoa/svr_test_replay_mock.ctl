// svr_test_replay_mock.ctl
//
// Run inside SVR_TEST after svr_test_create_dps.ctl. Reads
// mock_fmcs_raw.csv (EQP_NAME,PARAM_CODE,TRND_DATE,TAG_COMPRS_VAL, the same
// shape as a real TH_CM_FMCS_TRND extract - see sample image/trend data
// sample.png) and replays it into the DPs created above via dpSet, so
// CLI_TEST's trend/panels have something to display before the real FMCS
// extract exists.
//
// TRND_DATE format is "YY/MM/DD HH:MM:SS" (confirmed from the real extract
// screenshot). Do NOT parse it with a locale-guessing date function - split
// it explicitly, the same lesson that applies to the Python-side
// unpack_row() in TASKS.md (a bare pd.Timestamp(trnd_date) silently
// mis-parses this format for many dates).
//
// Usage:
//   WCCOActrl -proj SVR_TEST svr_test_replay_mock.ctl <mock_fmcs_raw.csv> <speed>
//   speed: samples-per-second replay rate multiplier (1 = real time = one
//   3-second sample every 3s; use e.g. 50 to compress a 2h rehearsal file
//   into a couple of minutes).

main(string csvPath = "mock_fmcs_raw.csv", float speed = 20.0)
{
  file f = fopen(csvPath, "r");
  if (f == 0)
  {
    DebugN("svr_test_replay_mock: cannot open " + csvPath);
    return;
  }

  string header;
  fgets(header, 4096, f);
  header = strrtrim(header, "\r\n");  // CSV is CRLF - see svr_test_create_dps.ctl
  dyn_string cols = strsplit(header, ",");
  int eqpCol = dynContains(cols, "EQP_NAME") - 1;
  int dateCol = dynContains(cols, "TRND_DATE") - 1;
  int valCol = dynContains(cols, "TAG_COMPRS_VAL") - 1;

  int nSet = 0, nSkippedNoDp = 0;
  string line;

  while (fgets(line, 8192, f) > 0)
  {
    line = strrtrim(line, "\r\n");
    if (line == "") continue;
    dyn_string parts = strsplit(line, ",");
    if (dynlen(parts) <= valCol) continue;

    string tag = parts[eqpCol + 1];
    if (!dpExists(tag))
    {
      nSkippedNoDp++;
      continue;
    }

    // TAG_COMPRS_VAL may itself contain no commas, so it's safe as the
    // trailing field even though we split the whole line on ",".
    string comprs = parts[valCol + 1];
    dyn_string pairs = strsplit(comprs, ";");
    for (int i = 1; i <= dynlen(pairs); i++)
    {
      dyn_string kv = strsplit(pairs[i], ":");
      if (dynlen(kv) != 2) continue;
      float val = (float)kv[2];
      dpSet(tag + ".value", val);
      nSet++;
      delay(0, (int)(1000.0 / speed));  // pace the replay; speed=samples/sec
    }
  }

  fclose(f);
  DebugN("svr_test_replay_mock: dpSet calls=" + nSet + " rows skipped (no DP)=" + nSkippedNoDp);
}
