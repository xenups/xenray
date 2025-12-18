# Country flag colors - primary and secondary colors for gradient effects
# Format: "country_code": ("primary_color", "secondary_color")
# Colors are dominant colors from each country's flag
# Note: White replaced with light/pale versions for better dark mode appearance

FLAG_COLORS = {
    # Europe
    "ad": ("#0018a8", "#d52b1e"),  # Andorra - Blue, Red
    "al": ("#e41e20", "#1a1a1a"),  # Albania - Red, Dark
    "am": ("#0033a0", "#d90012"),  # Armenia - Blue, Red
    "at": ("#ed2939", "#ff8080"),  # Austria - Red, Pale Red
    "az": ("#00b5e2", "#3f9c35"),  # Azerbaijan - Blue, Green
    "ba": ("#002395", "#fecb00"),  # Bosnia - Blue, Yellow
    "be": ("#1a1a1a", "#fdda24"),  # Belgium - Dark, Yellow
    "bg": ("#00966e", "#d62612"),  # Bulgaria - Green, Red
    "by": ("#c8313e", "#4aa657"),  # Belarus - Red, Green
    "ch": ("#ff0000", "#ff7777"),  # Switzerland - Red, Pale Red
    "cy": ("#d57800", "#4e5b31"),  # Cyprus - Orange, Green
    "cz": ("#11457e", "#d7141a"),  # Czech - Blue, Red
    "de": ("#1a1a1a", "#dd0000"),  # Germany - Dark, Red
    "dk": ("#c8102e", "#ff7070"),  # Denmark - Red, Pale Red
    "ee": ("#4891d9", "#1a1a1a"),  # Estonia - Blue, Dark
    "es": ("#aa151b", "#f1bf00"),  # Spain - Red, Yellow
    "fi": ("#002f6c", "#00d4ff"),  # Finland - Deep Blue, Electric Blue (Vibrant)
    "fr": ("#0055a4", "#ef4135"),  # France - Blue, Red
    "gb": ("#012169", "#c8102e"),  # UK - Blue, Red
    "ge": ("#ff0000", "#ff8888"),  # Georgia - Red, Pale Red
    "gr": ("#005bb8", "#00d4ff"),  # Greece - Vibrant Blue, Electric Blue
    "hr": ("#171796", "#ff0000"),  # Croatia - Blue, Red
    "hu": ("#cd2a3e", "#477050"),  # Hungary - Red, Green
    "ie": ("#169b62", "#ff883e"),  # Ireland - Green, Orange
    "is": ("#02529c", "#dc1e35"),  # Iceland - Blue, Red
    "it": ("#009246", "#ce2b37"),  # Italy - Green, Red
    "kz": ("#00afca", "#fec50c"),  # Kazakhstan - Blue, Yellow
    "lt": ("#fdb913", "#006a44"),  # Lithuania - Yellow, Green
    "lu": ("#ed2939", "#00a1de"),  # Luxembourg - Red, Blue
    "lv": ("#9e3039", "#d08090"),  # Latvia - Maroon, Pale Maroon
    "mc": ("#ce1126", "#ff7080"),  # Monaco - Red, Pale Red
    "md": ("#0046ae", "#cc092f"),  # Moldova - Blue, Red
    "me": ("#c40308", "#d4af3a"),  # Montenegro - Red, Gold
    "mk": ("#d20000", "#ffe600"),  # N. Macedonia - Red, Yellow
    "mt": ("#cf142b", "#ff7080"),  # Malta - Red, Pale Red
    "nl": ("#ae1c28", "#21468b"),  # Netherlands - Red, Blue
    "no": ("#ef2b2d", "#002868"),  # Norway - Red, Blue
    "pl": ("#dc143c", "#ff7080"),  # Poland - Red, Pale Red
    "pt": ("#ff0000", "#006600"),  # Portugal - Red, Green
    "ro": ("#002b7f", "#fcd116"),  # Romania - Blue, Yellow
    "rs": ("#0c4076", "#c6363c"),  # Serbia - Blue, Red
    "ru": ("#0039a6", "#d52b1e"),  # Russia - Blue, Red
    "se": ("#006aa7", "#fecc00"),  # Sweden - Blue, Yellow
    "si": ("#0000ff", "#ed1c24"),  # Slovenia - Blue, Red
    "sk": ("#0b4ea2", "#ee1c25"),  # Slovakia - Blue, Red
    "sm": ("#5eb6e4", "#88ccee"),  # San Marino - Blue, Pale Blue
    "ua": ("#0057b7", "#ffd700"),  # Ukraine - Blue, Yellow
    "va": ("#ffe000", "#ffee77"),  # Vatican - Yellow, Pale Yellow
    
    # Asia
    "ae": ("#00732f", "#ff0000"),  # UAE - Green, Red
    "af": ("#1a1a1a", "#009900"),  # Afghanistan - Dark, Green
    "bd": ("#006a4e", "#f42a41"),  # Bangladesh - Green, Red
    "bh": ("#ce1126", "#ff7080"),  # Bahrain - Red, Pale Red
    "bn": ("#f7e017", "#1a1a1a"),  # Brunei - Yellow, Dark
    "bt": ("#ff4e12", "#ffd520"),  # Bhutan - Orange, Yellow
    "cn": ("#de2910", "#ffde00"),  # China - Red, Yellow
    "hk": ("#de2910", "#ff9080"),  # Hong Kong - Red, Pale Red
    "id": ("#ff0000", "#ff8888"),  # Indonesia - Red, Pale Red
    "il": ("#0038b8", "#00d4ff"),  # Israel - Blue, Electric Blue
    "in": ("#ff9933", "#138808"),  # India - Orange, Green
    "iq": ("#ce1126", "#007a3d"),  # Iraq - Red, Green
    "ir": ("#00a651", "#77cc99"),  # Iran - Green, Pale Green
    "jo": ("#007a3d", "#ce1126"),  # Jordan - Green, Red
    "jp": ("#bc002d", "#ff8899"),  # Japan - Red, Pale Red
    "kg": ("#e8112d", "#ffef00"),  # Kyrgyzstan - Red, Yellow
    "kh": ("#032ea1", "#e00025"),  # Cambodia - Blue, Red
    "kr": ("#0047a0", "#c60c30"),  # S. Korea - Blue, Red
    "kw": ("#007a3d", "#ce1126"),  # Kuwait - Green, Red
    "la": ("#ce1126", "#002868"),  # Laos - Red, Blue
    "lb": ("#ed1c24", "#00a651"),  # Lebanon - Red, Green
    "lk": ("#8d153a", "#ffb700"),  # Sri Lanka - Maroon, Yellow
    "mm": ("#fecb00", "#34b233"),  # Myanmar - Yellow, Green
    "mn": ("#c4272f", "#015197"),  # Mongolia - Red, Blue
    "mo": ("#00785e", "#77bb99"),  # Macau - Green, Pale Green
    "mv": ("#d21034", "#007e3a"),  # Maldives - Red, Green
    "my": ("#010066", "#cc0001"),  # Malaysia - Blue, Red
    "np": ("#dc143c", "#003893"),  # Nepal - Red, Blue
    "om": ("#db161b", "#ff8888"),  # Oman - Red, Pale Red
    "ph": ("#0038a8", "#ce1126"),  # Philippines - Blue, Red
    "pk": ("#01411c", "#66aa77"),  # Pakistan - Green, Pale Green
    "ps": ("#007a3d", "#ce1126"),  # Palestine - Green, Red
    "qa": ("#8d1b3d", "#cc7799"),  # Qatar - Maroon, Pale Maroon
    "sa": ("#006c35", "#66aa77"),  # Saudi Arabia - Green, Pale Green
    "sg": ("#ed2939", "#ff8899"),  # Singapore - Red, Pale Red
    "sy": ("#ce1126", "#007a3d"),  # Syria - Red, Green
    "th": ("#a51931", "#2d2a4a"),  # Thailand - Red, Blue
    "tj": ("#cc0000", "#00cc00"),  # Tajikistan - Red, Green
    "tl": ("#dc241f", "#ffc726"),  # Timor-Leste - Red, Yellow
    "tm": ("#00843d", "#d22630"),  # Turkmenistan - Green, Red
    "tr": ("#e30a17", "#ff8888"),  # Turkey - Red, Pale Red
    "tw": ("#000095", "#fe0000"),  # Taiwan - Blue, Red
    "uz": ("#1eb53a", "#0099b5"),  # Uzbekistan - Green, Blue
    "vn": ("#da251d", "#ffff00"),  # Vietnam - Red, Yellow
    "ye": ("#ce1126", "#1a1a1a"),  # Yemen - Red, Dark
    
    # Americas
    "ar": ("#1199ff", "#00d4ff"),  # Argentina - Sky Blue, Cyan
    "bo": ("#ce1126", "#007934"),  # Bolivia - Red, Green
    "br": ("#009c3b", "#ffdf00"),  # Brazil - Green, Yellow
    "ca": ("#ff0000", "#ff8888"),  # Canada - Red, Pale Red
    "cl": ("#0039a6", "#d52b1e"),  # Chile - Blue, Red
    "co": ("#fcd116", "#003893"),  # Colombia - Yellow, Blue
    "cr": ("#002b7f", "#ce1126"),  # Costa Rica - Blue, Red
    "cu": ("#002a8f", "#cb1515"),  # Cuba - Blue, Red
    "do": ("#002d62", "#ce1126"),  # Dominican Rep - Blue, Red
    "ec": ("#ffd100", "#034ea2"),  # Ecuador - Yellow, Blue
    "gt": ("#4997d0", "#88bbee"),  # Guatemala - Blue, Pale Blue
    "hn": ("#0073cf", "#7799dd"),  # Honduras - Blue, Pale Blue
    "jm": ("#009b3a", "#fed100"),  # Jamaica - Green, Yellow
    "mx": ("#006847", "#ce1126"),  # Mexico - Green, Red
    "ni": ("#0067c6", "#7799dd"),  # Nicaragua - Blue, Pale Blue
    "pa": ("#da121a", "#005eb8"),  # Panama - Red, Blue
    "pe": ("#d91023", "#ff8888"),  # Peru - Red, Pale Red
    "pr": ("#ef3340", "#0050f0"),  # Puerto Rico - Red, Blue
    "py": ("#d52b1e", "#0038a8"),  # Paraguay - Red, Blue
    "sv": ("#0f47af", "#7799dd"),  # El Salvador - Blue, Pale Blue
    "us": ("#3c3b6e", "#b22234"),  # USA - Blue, Red
    "uy": ("#001489", "#7799dd"),  # Uruguay - Blue, Pale Blue
    "ve": ("#cf142b", "#00247d"),  # Venezuela - Red, Blue
    
    # Africa
    "ao": ("#cc092f", "#1a1a1a"),  # Angola - Red, Dark
    "bf": ("#ef2b2d", "#009e49"),  # Burkina Faso - Red, Green
    "bj": ("#e8112d", "#008751"),  # Benin - Red, Green
    "bw": ("#75aadb", "#1a1a1a"),  # Botswana - Blue, Dark
    "cd": ("#007fff", "#ce1021"),  # DR Congo - Blue, Red
    "cf": ("#003082", "#289728"),  # CAR - Blue, Green
    "cg": ("#009543", "#dc241f"),  # Congo - Green, Red
    "ci": ("#f77f00", "#009e60"),  # Ivory Coast - Orange, Green
    "cm": ("#007a5e", "#ce1126"),  # Cameroon - Green, Red
    "cv": ("#003893", "#cf2027"),  # Cape Verde - Blue, Red
    "dj": ("#6ab2e7", "#12ad2b"),  # Djibouti - Blue, Green
    "dz": ("#006233", "#d21034"),  # Algeria - Green, Red
    "eg": ("#ce1126", "#1a1a1a"),  # Egypt - Red, Dark
    "er": ("#ea0437", "#4189dd"),  # Eritrea - Red, Blue
    "et": ("#da121a", "#078930"),  # Ethiopia - Red, Green
    "ga": ("#009e49", "#fcd116"),  # Gabon - Green, Yellow
    "gh": ("#006b3f", "#ce1126"),  # Ghana - Green, Red
    "gm": ("#ce1126", "#0c1c8c"),  # Gambia - Red, Blue
    "gn": ("#ce1126", "#fcd116"),  # Guinea - Red, Yellow
    "gq": ("#3e9a00", "#e32118"),  # Eq. Guinea - Green, Red
    "gw": ("#ce1126", "#fcd116"),  # Guinea-Bissau - Red, Yellow
    "ke": ("#006600", "#bb0000"),  # Kenya - Green, Red
    "km": ("#003a80", "#ffc61e"),  # Comoros - Blue, Yellow
    "lr": ("#002868", "#bf0a30"),  # Liberia - Blue, Red
    "ls": ("#00209f", "#009543"),  # Lesotho - Blue, Green
    "ly": ("#e70013", "#239e46"),  # Libya - Red, Green
    "ma": ("#c1272d", "#006233"),  # Morocco - Red, Green
    "mg": ("#fc3d32", "#007e3a"),  # Madagascar - Red, Green
    "ml": ("#14b53a", "#fcd116"),  # Mali - Green, Yellow
    "mr": ("#006233", "#ffc400"),  # Mauritania - Green, Gold
    "mu": ("#1a206d", "#ea2839"),  # Mauritius - Blue, Red
    "mw": ("#ce1126", "#339e35"),  # Malawi - Red, Green
    "mz": ("#fce100", "#d21034"),  # Mozambique - Yellow, Red
    "na": ("#003580", "#009543"),  # Namibia - Blue, Green
    "ne": ("#0db02b", "#f77f00"),  # Niger - Green, Orange
    "ng": ("#008751", "#66bb88"),  # Nigeria - Green, Pale Green
    "rw": ("#00a1de", "#fad201"),  # Rwanda - Blue, Yellow
    "sc": ("#003d88", "#d62828"),  # Seychelles - Blue, Red
    "sd": ("#d21034", "#007229"),  # Sudan - Red, Green
    "sl": ("#1eb53a", "#0072c6"),  # Sierra Leone - Green, Blue
    "sn": ("#00853f", "#fdef42"),  # Senegal - Green, Yellow
    "so": ("#4189dd", "#88bbee"),  # Somalia - Blue, Pale Blue
    "ss": ("#078930", "#0f47af"),  # S. Sudan - Green, Blue
    "sz": ("#3e5eb9", "#ffd900"),  # Eswatini - Blue, Yellow
    "td": ("#002664", "#c60c30"),  # Chad - Blue, Red
    "tg": ("#006a4e", "#d21034"),  # Togo - Green, Red
    "tn": ("#e70013", "#ff8888"),  # Tunisia - Red, Pale Red
    "tz": ("#1eb53a", "#00a3dd"),  # Tanzania - Green, Blue
    "ug": ("#fcdc04", "#d90000"),  # Uganda - Yellow, Red
    "za": ("#007a4d", "#1a1a1a"),  # South Africa - Green, Dark
    "zm": ("#198a00", "#ef7d00"),  # Zambia - Green, Orange
    "zw": ("#319208", "#ffd200"),  # Zimbabwe - Green, Yellow
    
    # Oceania
    "au": ("#00008b", "#6666bb"),  # Australia - Blue, Pale Blue
    "fj": ("#68bfe5", "#002868"),  # Fiji - Blue, Navy
    "fm": ("#75b2dd", "#99ccee"),  # Micronesia - Blue, Pale Blue
    "ki": ("#ce1126", "#003f87"),  # Kiribati - Red, Blue
    "mh": ("#003893", "#f57f20"),  # Marshall Islands - Blue, Orange
    "nr": ("#002b7f", "#ffc61e"),  # Nauru - Blue, Yellow
    "nz": ("#00247d", "#6666bb"),  # New Zealand - Blue, Pale Blue
    "pg": ("#ce1126", "#1a1a1a"),  # Papua New Guinea - Red, Dark
    "pw": ("#4aadd6", "#ffde00"),  # Palau - Blue, Yellow
    "sb": ("#0051ba", "#215b33"),  # Solomon Islands - Blue, Green
    "to": ("#c10000", "#ff8888"),  # Tonga - Red, Pale Red
    "tv": ("#00247d", "#ffce00"),  # Tuvalu - Blue, Yellow
    "vu": ("#009543", "#d21034"),  # Vanuatu - Green, Red
    "ws": ("#ce1126", "#002b7f"),  # Samoa - Red, Blue
    
    # Default fallback
    "default": ("#6366f1", "#8b5cf6"),  # Indigo, Purple
}
