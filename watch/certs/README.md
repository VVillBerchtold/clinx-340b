# Intermediate certificates for the watch

This folder holds public intermediate certificates that the daily watch adds when it checks a
state's website. Some state servers send their own certificate without the intermediate that
links it to a trusted root, so a plain client cannot verify them. Checking is never switched
off. A certificate placed here is added to the checks, nothing more.

What belongs here: public intermediate certificates only, as `.pem`, `.crt` or `.cer` files.
Never a private key, and never a root that the system already trusts.

How to check one before adding it:

1. Open the site in a browser and view the certificate chain. Note the issuer of the site's
   certificate.
2. Download the intermediate from the issuer's own published list of certificates, not from the
   state site.
3. Compare its SHA-256 fingerprint with the one the issuer publishes.
4. Confirm it is signed by a root the system trusts:
   `openssl verify -CAfile <root bundle> <intermediate>.pem`.
5. Name the file for the site and issuer, and add a line to this README saying which site it is
   for and the day it was checked.

Certificates checked and added so far: none.
