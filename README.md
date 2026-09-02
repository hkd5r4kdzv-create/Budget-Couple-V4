# Notre Budget — V3 publiable

Application Flask mobile en français avec PostgreSQL.

## Déploiement Render

1. Mettre ces fichiers dans un dépôt GitHub.
2. Sur Render : New → Blueprint.
3. Connecter le dépôt.
4. Render lit `render.yaml`, crée le service web et PostgreSQL.
5. Attendre le déploiement.
6. Ouvrir l'URL Render puis `/setup`.
7. Créer le premier compte administrateur.
8. Dans Admin, créer le deuxième compte.

Les deux comptes partagent les mêmes données.

## Variables
Render génère `SECRET_KEY` et fournit `DATABASE_URL` via `render.yaml`.

## Local
Créer une base PostgreSQL puis :
DATABASE_URL="postgresql://..." SECRET_KEY="une-cle-longue" python app.py

## Important
Ne jamais mettre un mot de passe de base de données, SECRET_KEY ou autre secret dans GitHub.
