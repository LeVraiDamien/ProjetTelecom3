"""Outils communs aux xApps Python du scenario B : lecture d'un CSV qui grossit."""

import csv
import io
import signal
import time


class Stopper:
    """Arret propre sur SIGTERM/SIGINT (docker stop)."""

    def __init__(self):
        self.stop = False
        signal.signal(signal.SIGTERM, self._on)
        signal.signal(signal.SIGINT, self._on)

    def _on(self, *_):
        self.stop = True


def follow_csv(path, stopper, poll_s=0.25, drain_s=3.0):
    """Rend les lignes d'un CSV au fur et a mesure qu'un autre processus les ecrit.

    C'est le mecanisme d'echange applicatif entre xApps : un fichier CSV partage
    dans le repertoire du run. Seules les lignes COMPLETES (terminees par un saut
    de ligne) sont lues ; une ligne en cours d'ecriture est relue plus tard.
    Apres une demande d'arret, on continue drain_s secondes pour vider le fichier.
    """
    header, pos, buf, deadline = None, 0, "", None
    while True:
        try:
            with open(path, newline="") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
        except FileNotFoundError:
            chunk = ""
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if not line.strip():
                continue
            fields = next(csv.reader(io.StringIO(line)))
            if header is None:
                header = fields
            elif len(fields) == len(header):
                yield dict(zip(header, fields))
        if stopper.stop:
            deadline = deadline or time.time() + drain_s
            if not chunk and time.time() >= deadline:
                return
        time.sleep(poll_s)


def num(value):
    """Nombre ou None : une valeur vide ou invalide n'est jamais remplacee par 0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class CsvOut:
    def __init__(self, path, fields):
        self.f = open(path, "w", newline="")
        self.w = csv.DictWriter(self.f, fieldnames=fields)
        self.w.writeheader()
        self.f.flush()

    def write(self, row):
        self.w.writerow(row)
        self.f.flush()

    def close(self):
        self.f.close()
