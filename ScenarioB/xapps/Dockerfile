# Scenario B - xApps Python Edge-AI et gestion des ressources (image telecom-lab-p3-ai:1.0).
# Petit environnement CPU : aucune bibliotheque d'IA n'est necessaire a l'execution,
# l'arbre de decision est exporte en JSON par train_tree.py (qui, lui, utilise scikit-learn).
FROM python:3.12-slim
RUN pip install --no-cache-dir --root-user-action=ignore scikit-learn==1.5.2
WORKDIR /app
COPY common.py /app/common.py
COPY edge_ai /app/edge_ai
COPY resource_mgmt /app/resource_mgmt
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
