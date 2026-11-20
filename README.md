# NOVA STORE V3 — Boutique multi-produits (démo)

## Démarrage

Python 3.10+ recommandé.

```bash
python -m venv .venv
# macOS/Linux : source .venv/bin/activate
# Windows : .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Ouvrir http://127.0.0.1:8000 — Documentation API : http://127.0.0.1:8000/docs

## Fonctionnalités

- Catalogue 6 produits de démonstration ; recherche, catégorie, tri.
- Fiches produits individuelles, panier conservé dans le navigateur.
- API `GET /api/products`, `GET /api/products/{id}`, `POST /api/cart/quote`, `POST /api/orders/demo`, `GET /api/status`.
- Les prix sont calculés sur le serveur. Les brouillons sont enregistrés dans `store.db` (SQLite) avec identifiant aléatoire, sans données personnelles.
- **Aucun paiement, commande réelle, connexion AliExpress ou expédition.** Les montants de livraison et la fiscalité ne sont pas calculés. Le brouillon n'est pas une vente.

## Avant lancement commercial

Valider les fournisseurs et les échantillons, conformité et sécurité produit, documents légaux français, CGV, rétractation, politique de confidentialité, prix TTC et livraison, gestion des stocks et retours, authentification administrateur, Stripe avec webhooks signés et idempotence, suivi des commandes, e-mails transactionnels et déploiement sécurisé. Ne jamais activer un encaissement sans ces étapes.

Les visuels actuels sont des pictogrammes, pas des photos fournisseur. Les descriptions sont indicatives.
