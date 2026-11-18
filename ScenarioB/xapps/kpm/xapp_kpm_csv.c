/*
 * Scenario B - Phase 7 : xApp KPM etendue avec export CSV.
 *
 * Derivee de l'exemple FlexRIC examples/xApp/c/monitor/xapp_oran_moni.c
 * (OAI Public License 1.1), dont elle reprend la construction de l'abonnement
 * E2SM-KPM. Differences :
 *   - une seule chose : s'abonner aux mesures KPM listees dans le .conf et
 *     ecrire UNE ligne CSV par indication recue ;
 *   - tourne jusqu'a SIGTERM/SIGINT (ou KPM_DURATION_S secondes) au lieu de 10 s ;
 *   - les valeurs sont nommees d'apres l'ORDRE des actions de l'abonnement,
 *     car le gNB OCUDU ne renvoie pas la liste des noms dans l'indication
 *     (colonne names_in_indication = 0). Si des noms sont renvoyes, ils sont
 *     consignes tels quels dans reported_names pour verification.
 *
 * Variables d'environnement :
 *   KPM_CSV         chemin du fichier CSV (defaut /data/kpm.csv)
 *   RUN_ID          identifiant d'experience recopie dans chaque ligne
 *   KPM_DURATION_S  duree en secondes, 0 = jusqu'au signal (defaut 0)
 *
 * Champs non fournis par E2SM-KPM format 1 (identifiant d'UE, de cellule) :
 * ecrits "unavailable", jamais deduits.
 */

#include "../../../../src/xApp/e42_xapp_api.h"
#include "../../../../src/util/alg_ds/alg/defer.h"
#include "../../../../src/util/e2ap_ngran_types.h"
#include "../../../../src/sm/kpm_sm/kpm_sm_id_wrapper.h"

#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAX_MEAS 16

static pthread_mutex_t mtx = PTHREAD_MUTEX_INITIALIZER;
static FILE* csv = NULL;
static const char* run_id = "unset";
static char meas_names[MAX_MEAS][64];
static size_t n_meas = 0;
static uint64_t period_ms_sub = 0;
static double prev_epoch = 0.0;
static unsigned long n_ind = 0;
static volatile sig_atomic_t stop_flag = 0;

static void on_signal(int sig) { (void)sig; stop_flag = 1; }

static void sm_cb_kpm(sm_ag_if_rd_t const* rd, global_e2_node_id_t const* e2_node)
{
  assert(rd != NULL);
  assert(rd->type == INDICATION_MSG_AGENT_IF_ANS_V0);
  assert(rd->ind.type == KPM_STATS_V3_0);

  kpm_ind_data_t const* kpm = &rd->ind.kpm.ind;
  kpm_ric_ind_hdr_format_1_t const* hdr = &kpm->hdr.kpm_ric_ind_hdr_format_1;

  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);
  double epoch = ts.tv_sec + ts.tv_nsec / 1e9;
  struct tm tm_utc;
  gmtime_r(&ts.tv_sec, &tm_utc);
  char iso[40];
  strftime(iso, sizeof iso, "%Y-%m-%dT%H:%M:%S", &tm_utc);

  pthread_mutex_lock(&mtx);
  if (kpm->msg.type != FORMAT_1_INDICATION_MESSAGE) {
    fprintf(stderr, "[kpm_csv] indication ignoree : format %d (seul le format 1 est verifie)\n", kpm->msg.type);
    pthread_mutex_unlock(&mtx);
    return;
  }
  kpm_ind_msg_format_1_t const* m = &kpm->msg.frm_1;

  /* Valeurs a plat, dans l'ordre de reception. */
  double val[MAX_MEAS];
  char kind[MAX_MEAS];
  size_t n_val = 0, rec_len = 0;
  for (size_t i = 0; i < m->meas_data_lst_len; i++) {
    rec_len = m->meas_data_lst[i].meas_record_len;
    for (size_t j = 0; j < rec_len && n_val < MAX_MEAS; j++) {
      meas_record_lst_t const* r = &m->meas_data_lst[i].meas_record_lst[j];
      if (r->value == INTEGER_MEAS_VALUE) { val[n_val] = r->int_val; kind[n_val] = 'i'; }
      else if (r->value == REAL_MEAS_VALUE) { val[n_val] = r->real_val; kind[n_val] = 'r'; }
      else { val[n_val] = 0; kind[n_val] = 'n'; }
      n_val++;
    }
  }

  /* Noms eventuellement renvoyes par le gNB (verification de l'ordre). */
  char reported[512] = "";
  for (size_t z = 0; z < m->meas_info_lst_len; z++) {
    if (m->meas_info_lst[z].meas_type.type == NAME_MEAS_TYPE) {
      size_t len = m->meas_info_lst[z].meas_type.name.len;
      size_t used = strlen(reported);
      if (used + len + 2 < sizeof reported) {
        if (used) reported[used++] = '|';
        memcpy(reported + used, m->meas_info_lst[z].meas_type.name.buf, len);
        reported[used + len] = '\0';
      }
    }
  }

  fprintf(csv, "%s,%s.%03ldZ,%.3f,%lu,%lu,%.0f,%s,%d,unavailable,unavailable,%zu,%zu,%zu,%d,%s,%s",
          run_id, iso, ts.tv_nsec / 1000000, epoch, (unsigned long)hdr->collectStartTime,
          (unsigned long)period_ms_sub, prev_epoch > 0 ? (epoch - prev_epoch) * 1000.0 : -1.0,
          get_e2ap_ngran_name(e2_node->type), e2_node->nb_id.nb_id,
          (size_t)m->meas_data_lst_len, rec_len, n_val, m->meas_info_lst_len > 0 ? 1 : 0, reported,
          n_val == n_meas ? "ok" : "count_mismatch");
  for (size_t k = 0; k < n_meas; k++) {
    if (k < n_val && n_val == n_meas && kind[k] == 'i') fprintf(csv, ",%.0f", val[k]);
    else if (k < n_val && n_val == n_meas && kind[k] == 'r') fprintf(csv, ",%.6f", val[k]);
    else fprintf(csv, ",");                       /* valeur absente : laissee vide */
  }
  fprintf(csv, "\n");
  fflush(csv);
  prev_epoch = epoch;
  n_ind++;
  pthread_mutex_unlock(&mtx);
}

static kpm_event_trigger_def_t gen_kpm_ev_trig(uint64_t period)
{
  kpm_event_trigger_def_t dst = {0};
  dst.type = FORMAT_1_RIC_EVENT_TRIGGER;
  dst.kpm_ric_event_trigger_format_1.report_period_ms = period;
  return dst;
}

static meas_info_format_1_lst_t gen_meas_info(const act_name_id_t act)
{
  meas_info_format_1_lst_t dst = {0};
  dst.meas_type.type = NAME_MEAS_TYPE;
  dst.meas_type.name = cp_str_to_ba(act.name);          /* noms 3GPP TS 28.552 */
  dst.label_info_lst_len = 1;
  dst.label_info_lst = calloc(1, sizeof(label_info_lst_t));
  assert(dst.label_info_lst != NULL);
  dst.label_info_lst[0].noLabel = calloc(1, sizeof(enum_value_e));
  assert(dst.label_info_lst[0].noLabel != NULL);
  *dst.label_info_lst[0].noLabel = TRUE_ENUM_VALUE;
  return dst;
}

static kpm_act_def_t gen_kpm_act_def_frmt_1(const sub_oran_sm_t sub, uint32_t period_ms)
{
  kpm_act_def_t dst = {0};
  dst.type = FORMAT_1_ACTION_DEFINITION;
  dst.frm_1.gran_period_ms = period_ms;
  dst.frm_1.meas_info_lst_len = sub.act_len;
  dst.frm_1.meas_info_lst = calloc(sub.act_len, sizeof(meas_info_format_1_lst_t));
  assert(dst.frm_1.meas_info_lst != NULL);
  for (size_t i = 0; i < (size_t)sub.act_len; i++)
    dst.frm_1.meas_info_lst[i] = gen_meas_info(sub.actions[i]);
  return dst;
}

int main(int argc, char* argv[])
{
  fr_args_t args = init_fr_args(argc, argv);
  defer({ free_fr_args(&args); });

  const char* path = getenv("KPM_CSV") ? getenv("KPM_CSV") : "/data/kpm.csv";
  if (getenv("RUN_ID")) run_id = getenv("RUN_ID");
  int duration = getenv("KPM_DURATION_S") ? atoi(getenv("KPM_DURATION_S")) : 0;

  /* Premier abonnement KPM format 1 du .conf. */
  int sel = -1;
  for (int32_t j = 0; j < args.sub_oran_sm_len; j++)
    if (!strcasecmp(args.sub_oran_sm[j].name, "kpm") && args.sub_oran_sm[j].format == 1) { sel = j; break; }
  assert(sel >= 0 && "aucun abonnement KPM format 1 dans le .conf");
  sub_oran_sm_t const sub = args.sub_oran_sm[sel];
  assert(sub.act_len > 0 && sub.act_len <= MAX_MEAS);
  n_meas = sub.act_len;
  period_ms_sub = sub.time;
  for (size_t i = 0; i < n_meas; i++)
    snprintf(meas_names[i], sizeof meas_names[i], "%s", sub.actions[i].name);

  csv = fopen(path, "w");
  assert(csv != NULL && "impossible d'ouvrir le fichier CSV");
  fprintf(csv, "run_id,obs_time_utc,obs_epoch_s,collect_start_raw,requested_period_ms,delta_prev_ms,"
               "e2_node_type,e2_node_id,cell_id,ue_id,meas_data_lst_len,meas_record_len,n_values,"
               "names_in_indication,reported_names,mapping_status");
  for (size_t i = 0; i < n_meas; i++) fprintf(csv, ",%s", meas_names[i]);
  fprintf(csv, "\n");
  fflush(csv);

  signal(SIGTERM, on_signal);
  signal(SIGINT, on_signal);

  init_xapp_api(&args);
  sleep(1);
  e2_node_arr_xapp_t nodes = e2_nodes_xapp_api();
  defer({ free_e2_node_arr_xapp(&nodes); });
  assert(nodes.len > 0 && "aucun noeud E2 connecte au RIC");
  printf("[kpm_csv] noeuds E2 connectes = %d, CSV = %s, run_id = %s\n", nodes.len, path, run_id);

  sm_ans_xapp_t* handle = calloc(nodes.len, sizeof(sm_ans_xapp_t));
  assert(handle != NULL);
  int n_handle = 0;
  for (int i = 0; i < nodes.len; i++) {
    e2_node_connected_xapp_t* n = &nodes.n[i];
    if (strcasecmp(sub.ran_type, get_e2ap_ngran_name(n->id.type))) continue;

    kpm_sub_data_t kpm_sub = {0};
    defer({ free_kpm_sub_data(&kpm_sub); });
    kpm_sub.ev_trg_def = gen_kpm_ev_trig(period_ms_sub);
    kpm_sub.sz_ad = 1;
    kpm_sub.ad = calloc(1, sizeof(kpm_act_def_t));
    assert(kpm_sub.ad != NULL);
    *kpm_sub.ad = gen_kpm_act_def_frmt_1(sub, period_ms_sub);

    printf("[kpm_csv] abonnement KPM format 1, periode %lu ms, noeud %s id %d, mesures (dans l'ordre) :",
           (unsigned long)period_ms_sub, get_e2ap_ngran_name(n->id.type), n->id.nb_id.nb_id);
    for (size_t k = 0; k < n_meas; k++) printf(" %s", meas_names[k]);
    printf("\n");
    handle[n_handle] = report_sm_xapp_api(&n->id, SM_KPM_ID, &kpm_sub, sm_cb_kpm);
    assert(handle[n_handle].success == true);
    n_handle++;
  }
  assert(n_handle > 0 && "aucun noeud E2 du type demande (ran_type)");

  for (int t = 0; !stop_flag && (duration == 0 || t < duration); t++) sleep(1);

  for (int i = 0; i < n_handle; i++) rm_report_sm_xapp_api(handle[i].u.handle);
  free(handle);
  while (try_stop_xapp_api() == false) usleep(1000);
  pthread_mutex_lock(&mtx);
  fclose(csv);
  pthread_mutex_unlock(&mtx);
  printf("[kpm_csv] arret propre, %lu indications ecrites\n", n_ind);
  return 0;
}
