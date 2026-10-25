# DRAFT: Citizen Image-Submission Consent Notice & Privacy Policy

> [!IMPORTANT]
> **LEGAL NOTICE**: This draft policy is prepared for legal and privacy compliance review under India's *Digital Personal Data Protection (DPDP) Act, 2023*. It must receive formal legal sign-off before being deployed on public citizen upload interfaces.

### 1. Citizen Safety Advisory (Displayed Prominently Before Upload)
> ⚠️ **STAY SAFE! NEVER ENTER FLOODWATER OR ACTIVE TRAFFIC.**  
> Do NOT step into flowing water, standing floodwater of unknown depth, or active carriageways to capture photographs. Photographs must ONLY be taken from secure pedestrian sidewalks, foot overbridges, or safe elevated vantage points. Your personal safety is far more important than any photo.

---

### 2. Explicit Consent Checkbox Text (Mandatory Front-End Field)
```
[ ] I confirm that:
    1. I captured this photograph from a safe, legal, and publicly accessible vantage point without entering floodwater or moving traffic.
    2. I grant Sahaay AI a non-exclusive, royalty-free, perpetual license to use, process, and analyze this image for non-commercial public-safety flood intelligence research and AI model training.
    3. I understand that all identifiable human faces and vehicle license plates will be automatically blurred to protect privacy.
    4. I have read and agree to the Sahaay AI Citizen Privacy Notice.
```

---

### 3. Purpose of Processing (Section 4 & 5, DPDP Act 2023)
Sahaay AI processes citizen-submitted road imagery strictly for:
1. **Real-Time Hazard Verification**: Corroborating community flood reports to generate early-warning advisories for emergency response teams and fellow citizens.
2. **AI Model Training & Validation**: Training computer vision models to distinguish flooded roads from wet asphalt, puddles, and surface reflections.
3. **Hydrological Research**: Mapping localized waterlogging recurrence to assist urban drainage planning in Hyderabad.

We will **NEVER**:
- Sell, license, or monetize your images.
- Use your images for commercial advertising, marketing, or tracking.
- Apply facial recognition, biometric analysis, or personal profiling.

---

### 4. What Information We Collect and How We Anonymize It
1. **The Photograph**: The visual scene of the road surface. Upon upload, our automated privacy engine immediately blurs all human faces and vehicle registration plates.
2. **Metadata**: Capture timestamp and GPS coordinates extracted from image EXIF headers (or manually pinned by you).
3. **Location Coarsening**: In public dashboards or shared benchmark releases, coordinates are coarsened to approximately $\sim 1\text{ km}$ to prevent identifying private residential properties.
4. **Contributor Identity**: We do NOT require your name or national ID. If you choose to provide an email for upload verification, it is stored in hashed, pseudonymous form.

---

### 5. Data Retention and Your Right to Erasure
- **Retention Period**: Images and derived training tokens are stored for a maximum of 36 months, after which they are purged.
- **Right to Withdraw Consent / Erasure**: You have the right to request deletion of your photograph at any time. Simply submit your unique `acquisition_id` (displayed upon upload confirmation) to `privacy@sahaay.ai`. We will completely delete both raw and processed copies from our servers within 14 calendar days.

---

### 6. Data Fiduciary & Grievance Redressal
- **Data Fiduciary**: Sahaay AI Urban Flood Intelligence Initiative
- **Grievance Redressal Officer**: [Name, Designation, Official Email: `grievance@sahaay.ai`]
- **Jurisdiction**: Hyderabad, Telangana, India
