# Punjab Medical Leads Scraper

Scrapes **Doctors** and **Medical Stores / Pharmacies** for all 20 major Punjab cities.
One Excel file per city with two sheets inside: `🩺 Doctors` and `💊 Medical Stores`.

---

## 🚀 How to Use (No coding needed)

### Step 1 — Set up the repo
1. Create a **new GitHub repository** (public or private)
2. Upload all these files keeping the folder structure intact:
   ```
   scraper.py
   requirements.txt
   .github/
     workflows/
       scrape.yml
   ```
   > ⚠️ The `.github/workflows/` folder structure is important — GitHub needs it exactly like this

### Step 2 — Run it

1. Go to your repo on GitHub
2. Click the **"Actions"** tab at the top
3. Click **"Punjab Medical Leads Scraper"** in the left sidebar
4. Click the **"Run workflow"** button (top right)
5. Choose a city **or leave blank to scrape all 20 cities**
6. Click the green **"Run workflow"** button

### Step 3 — Download your files

When the run finishes (green checkmark ✅):
1. Click on the completed run
2. Scroll down to **"Artifacts"**
3. Click **"Punjab-Medical-Leads"** to download a ZIP with all Excel files

The files also get **saved directly in your repo** under the `output/` folder.

---

## 📋 What's in each Excel file

### Sheet 1 — 🩺 Doctors
| Column | Description |
|--------|-------------|
| Doctor Name | Full name |
| Specialty | e.g. Cardiologist, GP, Dentist |
| Clinic / Hospital | Practice name |
| Phone | Contact number |
| Address | Full address |
| Source | Marham.pk / Oladoc.com / Sehat.com.pk |

### Sheet 2 — 💊 Medical Stores
| Column | Description |
|--------|-------------|
| Store Name | Pharmacy / medical store name |
| Type | Medical Store / Pharmacy |
| Phone | Contact number |
| Address | Full address |
| Source | OpenStreetMap / Marham.pk / Google Places |

---

## 🗺️ Cities Covered
Lahore, Faisalabad, Rawalpindi, Gujranwala, Multan, Bahawalpur, Sargodha,
Sialkot, Sheikhupura, Rahim Yar Khan, Jhang, Gujrat, Sahiwal, Okara, Kasur,
Dera Ghazi Khan, Muzaffargarh, Chiniot, Hafizabad, Mandi Bahauddin

---

## 🔑 Optional: Google Places API (more medical store results)

To get extra medical store data from Google Maps:
1. Get a free API key from [Google Cloud Console](https://console.cloud.google.com)
2. In your GitHub repo go to **Settings → Secrets → Actions**
3. Add a secret named `GOOGLE_API_KEY` with your key

If you skip this, the scraper still works using OpenStreetMap and Marham.

---

## ⏱️ How long does it take?
- Single city: ~5–10 minutes
- All 20 cities: ~2–3 hours (GitHub gives you 2,000 free minutes/month)
