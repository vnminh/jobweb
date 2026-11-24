"""Vietnamese display labels for taxonomy values."""

GROUP_VI = {
    "G11": "Quản lý", "G13": "Kinh doanh & Tài chính", "G15": "Công nghệ thông tin", "G17": "Kiến trúc & Kỹ thuật",
    "G19": "Khoa học", "G21": "Công tác xã hội", "G23": "Pháp lý", "G25": "Giáo dục & Đào tạo",
    "G27": "Thiết kế, Nghệ thuật & Truyền thông", "G29": "Y tế – Chuyên môn", "G31": "Hỗ trợ y tế", "G33": "Bảo vệ & An ninh",
    "G35": "Nhà hàng & Ẩm thực", "G37": "Vệ sinh & Bảo trì", "G39": "Chăm sóc cá nhân & Dịch vụ", "G41": "Bán hàng",
    "G43": "Hành chính văn phòng", "G45": "Nông – Lâm – Ngư nghiệp", "G47": "Xây dựng", "G49": "Lắp đặt & Sửa chữa",
    "G51": "Sản xuất", "G53": "Vận tải & Kho vận", "G55": "Quân sự",
}
GROUP_VI_BY_NAME = {
    "Management": "G11", "Business and Financial Operations": "G13", "Computer and Mathematical": "G15", "Architecture and Engineering": "G17",
    "Life, Physical, and Social Science": "G19", "Community and Social Service": "G21", "Legal": "G23", "Educational Instruction and Library": "G25",
    "Arts, Design, Entertainment, Sports, and Media": "G27", "Healthcare Practitioners and Technical": "G29", "Healthcare Support": "G31",
    "Protective Service": "G33", "Food Preparation and Serving Related": "G35", "Building and Grounds Cleaning and Maintenance": "G37",
    "Personal Care and Service": "G39", "Sales and Related": "G41", "Office and Administrative Support": "G43",
    "Farming, Fishing, and Forestry": "G45", "Construction and Extraction": "G47", "Installation, Maintenance, and Repair": "G49",
    "Production": "G51", "Transportation and Material Moving": "G53", "Military Specific": "G55",
}
JOB_TYPE_VI = {"full_time": "Toàn thời gian", "part_time": "Bán thời gian", "contract": "Hợp đồng", "temporary": "Thời vụ", "internship": "Thực tập"}
JOB_TYPE_VI_BY_NAME = {"full-time": "Toàn thời gian", "part-time": "Bán thời gian", "contract": "Hợp đồng", "temporary": "Thời vụ", "internship": "Thực tập"}
SEN_VI = {"entry": "Mới đi làm", "mid": "Nhân viên", "senior": "Chuyên viên cao cấp", "manager": "Quản lý", "executive": "Giám đốc"}
DEGREE_VI = ["Không yêu cầu", "Trung học phổ thông", "Trung cấp nghề", "Cao đẳng", "Đại học", "Thạc sĩ", "Tiến sĩ"]
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "Washington D.C.", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "Virgin Islands", "AE": "Quân đội (AE)", "AP": "Quân đội (AP)", "AA": "Quân đội (AA)",
}


def state_name(s: str | None) -> str | None:
    return STATE_NAMES.get(s or "", s)
