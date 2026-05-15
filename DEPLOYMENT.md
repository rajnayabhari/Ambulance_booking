# 🚀 Comprehensive Deployment Guide: Ambulance Booking Project (RHEL 10 Edition)

This guide provides an exhaustive, step-by-step breakdown of deploying the Ambulance Booking project to an **AWS EC2 instance running RHEL 10** using Podman, Caddy, and your DuckDNS domain: `moteykoambulance.duckdns.org`.

---

## 🛠 Phase 1: Server Preparation (RHEL 10)

RHEL uses `dnf` instead of `apt`, and has `firewalld` enabled by default.

### 1. Update System Packages
```bash
sudo dnf update -y
```

### 2. Install Podman & Podman-Compose
Podman is native to RHEL and highly recommended.
```bash
# Install Podman and common tools
sudo dnf install -y podman podman-compose python3-pip

# Enable Podman socket for rootless compose (if needed)
systemctl --user enable --now podman.socket
```

### 3. Configure OS Firewall (`firewalld`)
In RHEL, you must open ports in the OS firewall *in addition* to the AWS Security Group.
```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 4. Configure AWS Security Group
Go to your AWS Console > EC2 > Security Groups. Add "Inbound Rules":
- **Type: HTTP** | Port: 80 | Source: 0.0.0.0/0
- **Type: HTTPS** | Port: 443 | Source: 0.0.0.0/0

---

## 📂 Phase 2: Project Transfer & Setup

### 4. Transfer the Project
You have three main ways to get your code onto the EC2 instance. Choose the one that fits your workflow:

#### Option A: Git Clone (Recommended)
If your code is on GitHub/GitLab, this is the cleanest method.
```bash
sudo dnf install -y git
git clone https://github.com/your-username/Ambulance_booking.git
cd Ambulance_booking
```

#### Option B: SCP (Fastest for local files)
Run this from your **local machine** (not the EC2):
```bash
scp -r /path/to/Ambulance_booking user@your-ec2-ip:/home/user/
```

#### Option C: ZIP & Upload
1. ZIP the project locally.
2. Upload via AWS Instance Connect or SFTP.
3. Unzip on the instance: `sudo dnf install -y unzip && unzip project.zip`.

### 5. Create Environment File (`.env`)
```bash
cp .env.example .env
nano .env
```
**Apply your specific settings:**
- `DUCKDNS_DOMAIN`: `moteykoambulance.duckdns.org`
- `DB_PASSWORD`: (Set a strong password)
- `SECRET_KEY`: `python3 -c 'import os; print(os.urandom(24).hex())'`
- `ADMIN_EMAIL`: (Your admin email)
- `ADMIN_PASSWORD`: (Your admin password)

---

## 🚀 Phase 3: Continuous Deployment (Optional but Recommended)

For your **real-world VPS deployment in 3 days**, you should use a simple pipeline:

1. **GitHub Actions**: Create a `.github/workflows/deploy.yml` that SSHs into your VPS and runs:
   ```bash
   cd /home/user/Ambulance_booking && git pull && podman-compose up -d --build
   ```
2. **Manual "Pipeline"**: For now, just run these commands manually after every change:
   ```bash
   git pull
   podman-compose up -d --build
   ```

---

## 🐳 Phase 4: Containerization Deep Dive

### 6. The Build Process (`Containerfile`)
On RHEL 10, Podman performs these "Micro-steps":
1. **`FROM python:3.11-slim`**: Base image.
2. **`RUN apt-get install ...`**: (Note: The Containerfile uses `apt` because the *container* is Debian-based, even if the *host* is RHEL).
3. **`USER appuser`**: Essential security.

### 7. Orchestration (`podman-compose.yaml`)
- **`db`**: PostgreSQL 15 with persistent volume.
- **`app`**: Your Flask application.
- **`proxy`**: Caddy handling SSL for `moteykoambulance.duckdns.org`.

---

## 🚀 Phase 5: Execution

### 8. Build and Start
```bash
podman-compose up -d --build
```

### 9. Automate DuckDNS Updates
```bash
mkdir -p ~/duckdns
cat <<EOF > ~/duckdns/duck.sh
#!/bin/bash
# Your domain: moteykoambulance
echo "url=\"https://www.duckdns.org/update?domains=moteykoambulance&token=YOUR_TOKEN_HERE&ip=\"" | curl -k -o ~/duckdns/duck.log -K -
EOF
chmod +x ~/duckdns/duck.sh

# Add to Crontab
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
```

---

## 🔍 Phase 6: Verification & Commands

### 10. Check if it's running
```bash
podman ps
```

### 11. Read Logs
```bash
podman-compose logs -f
```

### 12. SELinux Check (RHEL Specific)
If you get "Permission Denied" errors, it might be SELinux. To allow containers to access your files:
```bash
sudo chcon -Rt svirt_sandbox_file_t /home/zion/Ambulance_booking
```

---

## 🛑 Phase 7: Maintenance

### Restarting
```bash
podman-compose restart
```

### Stopping
```bash
podman-compose down
```
