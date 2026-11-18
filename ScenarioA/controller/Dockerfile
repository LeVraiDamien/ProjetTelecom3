# Scenario A - controleur OS-Ken (image telecom-lab-osken:1.0)
# Versions figees comme dans l'implementation de reference du sujet.
FROM python:3.11.5-slim

RUN pip install --no-cache-dir --root-user-action=ignore os-ken==3.1.1

WORKDIR /app
COPY learning_switch.py classifier_switch.py /app/

# OpenFlow : TCP 6633 (le conteneur tourne en --network host)
EXPOSE 6633
ENV PYTHONUNBUFFERED=1

CMD ["osken-manager", "--ofp-tcp-listen-port", "6633", "--verbose", "/app/learning_switch.py"]
