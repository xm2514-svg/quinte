# QUINTE-X — Procédure de compilation APK

## 1. Tester l'app sur PC d'abord (Windows)

```bash
cd C:\claude agent\Apprendre CLaude\Apprendre Claude\XAVPRO\quinte-x\quinte_x_app
pip install kivy
python main.py
```

Tu dois voir une fenêtre avec le top 5 du jour.

---

## 2. Compiler en APK (WSL Ubuntu requis)

### Une seule fois — installation WSL2 + Buildozer

Si WSL n'est pas installé, ouvre PowerShell admin et tape :

```powershell
wsl --install -d Ubuntu
```

Puis redémarre le PC. Au premier lancement Ubuntu, crée ton user.

### Dans Ubuntu (WSL), installation des dépendances

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git zip unzip openjdk-17-jdk \
    autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
    libtinfo5 cmake libffi-dev libssl-dev
pip3 install --user buildozer cython==0.29.36
```

Ajoute `~/.local/bin` au PATH si nécessaire :
```bash
echo 'export PATH=$PATH:~/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

### Copier le projet dans WSL

```bash
mkdir -p ~/quinte-x-app
cp -r /mnt/c/claude\ agent/Apprendre\ CLaude/Apprendre\ Claude/XAVPRO/quinte-x/quinte_x_app/* ~/quinte-x-app/
cd ~/quinte-x-app
```

### Lancer la compilation

```bash
buildozer android debug
```

**Première fois : 30 à 60 min** (téléchargement Android SDK/NDK/Gradle). Les fois suivantes : 2-5 min.

L'APK sera créé dans `~/quinte-x-app/bin/quintex-0.1.0-arm64-v8a_armeabi-v7a-debug.apk`

### Récupérer l'APK sur Windows

```bash
cp ~/quinte-x-app/bin/*.apk /mnt/c/claude\ agent/Apprendre\ CLaude/Apprendre\ Claude/XAVPRO/quinte-x/
```

---

## 3. Installer l'APK sur tablette Android

1. Sur la tablette : Paramètres → Sécurité → Activer "Sources inconnues"
2. Transférer l'APK (USB, Drive, email...)
3. Ouvrir le fichier APK depuis l'explorateur de fichiers → Installer

---

## 4. Mise à jour quotidienne du JSON

Pour que l'app affiche les données du jour (et non celles embarquées) :

**Option A : JSON local mis à jour par push GitHub** (recommandé)
- Pousse `quinte_x_top5.json` sur ton repo `quinte-x`
- Dans `main.py`, remplace `find_data_file()` par un fetch HTTPS :

```python
import urllib.request
def load_data():
    url = "https://raw.githubusercontent.com/<ton-user>/quinte-x/main/data/quinte_x_top5.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": f"Fetch GitHub échoué : {e}"}
```

**Option B : JSON embarqué (démo statique)**
- Recompile l'APK chaque jour avec le nouveau JSON. Pas viable à long terme.
