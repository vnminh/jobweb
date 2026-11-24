"""Sample seeker profiles and job postings for quickly creating test data. Values are resolved against the taxonomy
tables (O*NET codes, graph city keys, skill nodes) so a sample is always valid input for the recommender."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import City, Occupation, Skill

SEEKERS = [
    {"label": "Y tá – Houston, TX", "full_name": "Nguyễn Thu Hà", "city_key": "houston|TX", "zip5": "77030", "degree_ord": 4, "major": "Nursing",
     "graduation_date": "2016-05-15", "total_years_experience": 6, "currently_employed": True, "managed_others": False, "managed_how_many": 0,
     "last_occ": "29-1141.00", "history": ["Registered Nurse", "Patient Care Technician", "Certified Nursing Assistant"]},
    {"label": "Kế toán – Chicago, IL", "full_name": "Trần Minh Quân", "city_key": "chicago|IL", "zip5": "60601", "degree_ord": 4, "major": "Accounting",
     "graduation_date": "2018-06-01", "total_years_experience": 4, "currently_employed": True, "managed_others": False, "managed_how_many": 0,
     "last_occ": "13-2011.00", "history": ["Staff Accountant", "Accounts Payable Clerk"]},
    {"label": "Lập trình viên – San Jose, CA", "full_name": "Lê Hoàng Nam", "city_key": "san jose|CA", "zip5": "95113", "degree_ord": 5, "major": "Computer Science",
     "graduation_date": "2014-06-01", "total_years_experience": 8, "currently_employed": True, "managed_others": True, "managed_how_many": 3,
     "last_occ": "15-1252.00", "history": ["Senior Software Engineer", "Software Engineer", "Web Developer"]},
    {"label": "Nhân viên kho – Atlanta, GA", "full_name": "Phạm Văn Tài", "city_key": "atlanta|GA", "zip5": "30303", "degree_ord": 1, "major": "",
     "graduation_date": "", "total_years_experience": 2, "currently_employed": False, "managed_others": False, "managed_how_many": 0,
     "last_occ": "53-7062.00", "history": ["Warehouse Associate", "Forklift Operator"]},
    {"label": "Chăm sóc khách hàng – Phoenix, AZ", "full_name": "Võ Ngọc Lan", "city_key": "phoenix|AZ", "zip5": "85004", "degree_ord": 1, "major": "",
     "graduation_date": "", "total_years_experience": 3, "currently_employed": True, "managed_others": False, "managed_how_many": 0,
     "last_occ": "43-4051.00", "history": ["Customer Service Representative", "Cashier"]},
]

JOBS = [
    {"label": "Y tá ICU – Houston, TX", "title": "Registered Nurse - ICU (Full Time)", "city_key": "houston|TX", "zip5": "77030",
     "description": "Our hospital is hiring an experienced Registered Nurse for the Intensive Care Unit. You will provide direct patient care, monitor critically ill patients, administer medications and work closely with physicians and the care team. 12-hour shifts, full time.",
     "requirements": "Current RN license in Texas. Bachelor degree in Nursing preferred. At least 2 years of acute care experience. Strong communication skills and attention to detail.",
     "occupation_code": "29-1141.03", "job_type": "full_time", "seniority": "mid", "degree_req": 4, "years_req": 2,
     "skills": ["Patient Care", "Communication Skills", "Attention to Detail"]},
    {"label": "Kế toán viên – Chicago, IL", "title": "Staff Accountant", "city_key": "chicago|IL", "zip5": "60601",
     "description": "Growing distribution company seeks a Staff Accountant to handle month-end close, general ledger reconciliations, accounts payable and payroll support. You will prepare journal entries and assist with audits.",
     "requirements": "Bachelor degree in Accounting. 2+ years of experience. Proficient in Microsoft Excel and Intuit QuickBooks.",
     "occupation_code": "13-2011.00", "job_type": "full_time", "seniority": "mid", "degree_req": 4, "years_req": 2,
     "skills": ["General Ledger", "Accounts Payable", "Payroll", "Microsoft Excel", "Intuit QuickBooks"]},
    {"label": "Kỹ sư phần mềm – San Jose, CA", "title": "Senior Software Engineer (Python / JavaScript)", "city_key": "san jose|CA", "zip5": "95113",
     "description": "Join our product team to design and build scalable web services. You will write Python back-end services and JavaScript front-end code, review code, and mentor junior engineers. We use Git, Linux and Microsoft SQL Server.",
     "requirements": "BS/MS in Computer Science. 5+ years of professional software development experience.",
     "occupation_code": "15-1252.00", "job_type": "full_time", "seniority": "senior", "degree_req": 4, "years_req": 5,
     "skills": ["Python", "JavaScript", "Git", "Linux", "Microsoft SQL Server"]},
    {"label": "Nhân viên kho – Atlanta, GA", "title": "Warehouse Associate - 2nd Shift", "city_key": "atlanta|GA", "zip5": "30303",
     "description": "Busy distribution center needs Warehouse Associates for picking, packing, shipping and receiving. Forklift experience is a plus. Paid weekly.",
     "requirements": "High school diploma or GED. Able to lift 50 lbs. Forklift certification preferred.",
     "occupation_code": "53-7062.00", "job_type": "temporary", "seniority": "entry", "degree_req": 1, "years_req": None,
     "skills": ["Shipping and Receiving", "Forklift", "Warehouse Operations", "Inventory Control"]},
    {"label": "CSKH – Phoenix, AZ", "title": "Customer Service Representative", "city_key": "phoenix|AZ", "zip5": "85004",
     "description": "Answer inbound customer calls, resolve billing questions and enter orders. Paid training provided. Part time and full time schedules available.",
     "requirements": "High school diploma. 1 year of customer service experience. Data entry skills.",
     "occupation_code": "43-4051.00", "job_type": "part_time", "seniority": "entry", "degree_req": 1, "years_req": 1,
     "skills": ["Customer Service", "Data Entry", "Communication Skills"]},
]


def resolved(db: Session) -> dict:
    """Templates with names resolved to keys; entries whose city/occupation is missing are dropped."""
    skill_key = {s.name: s.key for s in db.query(Skill)}
    occ = {o.key: o for o in db.query(Occupation)}

    def city(k):
        return db.get(City, k)

    seekers = []
    for s in SEEKERS:
        c = city(s["city_key"])
        if c is None:
            continue
        seekers.append(dict(s, state=c.state, city=c.name, last_occ_name=occ[s["last_occ"]].name if s["last_occ"] in occ else None))
    jobs = []
    for j in JOBS:
        c = city(j["city_key"])
        if c is None:
            continue
        jobs.append(dict(j, state=c.state, city=c.name, occupation=occ[j["occupation_code"]].name if j["occupation_code"] in occ else None,
                         skills=[skill_key[n] for n in j["skills"] if n in skill_key]))
    return {"seekers": seekers, "jobs": jobs}
