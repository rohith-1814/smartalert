from __future__ import annotations

import json
import math
import os
import queue
import re
import sys
import threading
import uuid
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
STATE_FILE = Path(os.environ.get("SMARTALERT_STATE_FILE", ROOT / "smartalert-state.json"))
HOST = os.environ.get("SMARTALERT_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
MAX_BODY_BYTES = 32_000
MAX_ALERTS = 300
MAX_EMERGENCY_INCIDENTS = 1000

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    WebPushException = None
    webpush = None


TRANSLATIONS = {
    "en": {
        "accident": ("Road accident", "A road accident has been reported near {place}. Please slow down, keep a safe distance, and make way for emergency responders."),
        "breakdown": ("Vehicle breakdown", "A vehicle has broken down near {place}. Please pass carefully and offer help only when it is safe."),
        "fire": ("Fire reported", "A fire has been reported near {place}. Keep clear of the area and contact emergency services if needed."),
        "medical": ("Medical emergency", "A medical emergency has been reported near {place}. Give responders space and offer assistance only if it is safe."),
        "roadblock": ("Road blocked", "A road blockage has been reported near {place}. Slow down and consider an alternate route."),
        "vehicle": ("Vehicle-specific road alert", "A road hazard has been reported near {place}. Drivers of the notified vehicle type should slow down and use caution."),
        "other": ("Community emergency", "An emergency has been reported near {place}. Please stay alert and follow responder instructions."),
    },
    "hi": {
        "accident": ("सड़क दुर्घटना", "{place} के पास सड़क दुर्घटना की सूचना मिली है। धीरे चलें, सुरक्षित दूरी रखें और आपातकालीन वाहनों को रास्ता दें।"),
        "breakdown": ("वाहन खराब", "{place} के पास एक वाहन खराब हुआ है। सावधानी से निकलें और सुरक्षित होने पर ही सहायता करें।"),
        "fire": ("आग की सूचना", "{place} के पास आग की सूचना मिली है। क्षेत्र से दूर रहें और आवश्यकता पड़ने पर आपातकालीन सेवाओं से संपर्क करें।"),
        "medical": ("चिकित्सा आपातकाल", "{place} के पास चिकित्सा आपातकाल की सूचना मिली है। बचाव दल को जगह दें और सुरक्षित होने पर ही सहायता करें।"),
        "roadblock": ("सड़क अवरुद्ध", "{place} के पास सड़क अवरुद्ध है। गति धीमी करें और वैकल्पिक मार्ग अपनाएं।"),
        "vehicle": ("वाहन के लिए सड़क सूचना", "{place} के पास सड़क पर खतरे की सूचना है। सूचित वाहन चलाने वाले गति धीमी करें और सावधानी बरतें।"),
        "other": ("सामुदायिक आपातकाल", "{place} के पास आपातकाल की सूचना मिली है। सतर्क रहें और बचाव दल के निर्देशों का पालन करें।"),
    },
    "ta": {
        "accident": ("சாலை விபத்து", "{place} அருகே சாலை விபத்து ஏற்பட்டுள்ளது. வேகத்தைக் குறைத்து, பாதுகாப்பான இடைவெளி விட்டு, அவசர ஊர்திகளுக்கு வழிவிடுங்கள்."),
        "breakdown": ("வாகனம் பழுது", "{place} அருகே ஒரு வாகனம் பழுதடைந்துள்ளது. கவனமாக செல்லுங்கள்; பாதுகாப்பாக இருந்தால் மட்டுமே உதவுங்கள்."),
        "fire": ("தீ விபத்து", "{place} அருகே தீ ஏற்பட்டுள்ளது. அந்தப் பகுதியைத் தவிர்த்து, தேவைப்பட்டால் அவசர சேவைகளை அழைக்கவும்."),
        "medical": ("மருத்துவ அவசரம்", "{place} அருகே மருத்துவ அவசரம் ஏற்பட்டுள்ளது. மீட்புப் பணியாளர்களுக்கு இடமளித்து, பாதுகாப்பாக இருந்தால் மட்டுமே உதவுங்கள்."),
        "roadblock": ("சாலைத் தடை", "{place} அருகே சாலைத் தடை ஏற்பட்டுள்ளது. வேகத்தைக் குறைத்து மாற்றுப் பாதையைப் பயன்படுத்துங்கள்."),
        "vehicle": ("வாகனத்திற்கான சாலை எச்சரிக்கை", "{place} அருகே சாலை ஆபத்து பதிவாகியுள்ளது. அறிவிக்கப்பட்ட வகை வாகன ஓட்டிகள் வேகத்தைக் குறைத்து கவனமாக செல்லவும்."),
        "other": ("சமூக அவசரம்", "{place} அருகே அவசர நிலை பதிவாகியுள்ளது. விழிப்புடன் இருந்து மீட்புப் பணியாளர்களின் அறிவுறுத்தல்களைப் பின்பற்றுங்கள்."),
    },
    "te": {
        "accident": ("రోడ్డు ప్రమాదం", "{place} సమీపంలో రోడ్డు ప్రమాదం జరిగినట్లు సమాచారం. వేగం తగ్గించి, సురక్షిత దూరం పాటించి, అత్యవసర వాహనాలకు దారి ఇవ్వండి."),
        "breakdown": ("వాహనం నిలిచిపోయింది", "{place} సమీపంలో వాహనం నిలిచిపోయింది. జాగ్రత్తగా వెళ్లండి; సురక్షితంగా ఉంటేనే సహాయం చేయండి."),
        "fire": ("అగ్ని ప్రమాదం", "{place} సమీపంలో అగ్ని ప్రమాదం జరిగినట్లు సమాచారం. ఆ ప్రాంతానికి దూరంగా ఉండి, అవసరమైతే అత్యవసర సేవలకు కాల్ చేయండి."),
        "medical": ("వైద్య అత్యవసరం", "{place} సమీపంలో వైద్య అత్యవసరం ఉంది. సహాయక సిబ్బందికి దారి ఇవ్వండి; సురక్షితంగా ఉంటేనే సహాయం చేయండి."),
        "roadblock": ("రోడ్డు దిగ్బంధం", "{place} సమీపంలో రోడ్డు దిగ్బంధం ఉంది. వేగం తగ్గించి ప్రత్యామ్నాయ మార్గాన్ని ఎంచుకోండి."),
        "vehicle": ("వాహనానికి రహదారి హెచ్చరిక", "{place} సమీపంలో రహదారి ప్రమాదం నమోదైంది. సూచించిన వాహన రకం డ్రైవర్లు వేగం తగ్గించి జాగ్రత్తగా వెళ్లండి."),
        "other": ("సమాజ అత్యవసరం", "{place} సమీపంలో అత్యవసర పరిస్థితి నమోదైంది. అప్రమత్తంగా ఉండి సహాయక సిబ్బంది సూచనలు పాటించండి."),
    },
    "bn": {
        "accident": ("সড়ক দুর্ঘটনা", "{place}-এর কাছে সড়ক দুর্ঘটনার খবর পাওয়া গেছে। গতি কমান, নিরাপদ দূরত্ব রাখুন এবং জরুরি যানবাহনকে পথ দিন।"),
        "breakdown": ("গাড়ি বিকল", "{place}-এর কাছে একটি গাড়ি বিকল হয়েছে। সাবধানে পাশ কাটান এবং নিরাপদ হলেই সাহায্য করুন।"),
        "fire": ("আগুনের খবর", "{place}-এর কাছে আগুন লাগার খবর পাওয়া গেছে। এলাকা এড়িয়ে চলুন এবং প্রয়োজনে জরুরি পরিষেবায় যোগাযোগ করুন।"),
        "medical": ("চিকিৎসা জরুরি অবস্থা", "{place}-এর কাছে চিকিৎসা জরুরি অবস্থা ঘটেছে। উদ্ধারকারীদের জায়গা দিন এবং নিরাপদ হলেই সাহায্য করুন।"),
        "roadblock": ("রাস্তা বন্ধ", "{place}-এর কাছে রাস্তা বন্ধ রয়েছে। গতি কমান এবং বিকল্প পথ ব্যবহার করুন।"),
        "vehicle": ("নির্দিষ্ট যানবাহনের জন্য সড়ক সতর্কতা", "{place}-এর কাছে সড়ক বিপদের খবর পাওয়া গেছে। সতর্ক করা যানবাহনের চালকেরা গতি কমান এবং সাবধানে চলুন।"),
        "other": ("সম্প্রদায়ের জরুরি অবস্থা", "{place}-এর কাছে জরুরি অবস্থার খবর পাওয়া গেছে। সতর্ক থাকুন এবং উদ্ধারকারীদের নির্দেশ মেনে চলুন।"),
    },
    "mr": {
        "accident": ("रस्ते अपघात", "{place} जवळ रस्ते अपघाताची माहिती मिळाली आहे. वेग कमी करा, सुरक्षित अंतर ठेवा आणि आपत्कालीन वाहनांना वाट द्या."),
        "breakdown": ("वाहन बंद पडले", "{place} जवळ वाहन बंद पडले आहे. सावधपणे पुढे जा आणि सुरक्षित असल्यासच मदत करा."),
        "fire": ("आगीची माहिती", "{place} जवळ आग लागल्याची माहिती मिळाली आहे. परिसरापासून दूर राहा आणि गरज असल्यास आपत्कालीन सेवांशी संपर्क साधा."),
        "medical": ("वैद्यकीय आणीबाणी", "{place} जवळ वैद्यकीय आणीबाणी आहे. बचाव पथकांना जागा द्या आणि सुरक्षित असल्यासच मदत करा."),
        "roadblock": ("रस्ता बंद", "{place} जवळ रस्ता बंद आहे. वेग कमी करा आणि पर्यायी मार्ग निवडा."),
        "vehicle": ("वाहनासाठी रस्ता सूचना", "{place} जवळ रस्त्यावरील धोक्याची माहिती मिळाली आहे. सूचित वाहनचालकांनी वेग कमी करून सावधपणे जावे."),
        "other": ("समुदाय आणीबाणी", "{place} जवळ आणीबाणीची माहिती मिळाली आहे. सतर्क राहा आणि बचाव पथकांच्या सूचनांचे पालन करा."),
    },
    "gu": {
        "accident": ("રસ્તા અકસ્માત", "{place} નજીક રસ્તા અકસ્માતની જાણ થઈ છે. ગતિ ધીમી કરો, સુરક્ષિત અંતર રાખો અને કટોકટીના વાહનોને રસ્તો આપો."),
        "breakdown": ("વાહન બંધ પડ્યું", "{place} નજીક વાહન બંધ પડ્યું છે. સાવચેતીથી પસાર થાઓ અને સુરક્ષિત હોય ત્યારે જ મદદ કરો."),
        "fire": ("આગની જાણ", "{place} નજીક આગની જાણ થઈ છે. વિસ્તારથી દૂર રહો અને જરૂર પડે તો કટોકટી સેવાઓનો સંપર્ક કરો."),
        "medical": ("તબીબી કટોકટી", "{place} નજીક તબીબી કટોકટી છે. બચાવકર્મીઓને જગ્યા આપો અને સુરક્ષિત હોય ત્યારે જ મદદ કરો."),
        "roadblock": ("રસ્તો બંધ", "{place} નજીક રસ્તો બંધ છે. ગતિ ધીમી કરો અને વૈકલ્પિક માર્ગ અપનાવો."),
        "vehicle": ("વાહન માટે માર્ગ ચેતવણી", "{place} નજીક રસ્તાના જોખમની જાણ થઈ છે. સૂચિત વાહનના ચાલકોએ ગતિ ધીમી કરીને સાવચેતી રાખવી."),
        "other": ("સમુદાય કટોકટી", "{place} નજીક કટોકટીની જાણ થઈ છે. સતર્ક રહો અને બચાવકર્મીઓની સૂચનાઓનું પાલન કરો."),
    },
    "kn": {
        "accident": ("ರಸ್ತೆ ಅಪಘಾತ", "{place} ಬಳಿ ರಸ್ತೆ ಅಪಘಾತ ಸಂಭವಿಸಿದೆ. ವೇಗ ಕಡಿಮೆ ಮಾಡಿ, ಸುರಕ್ಷಿತ ಅಂತರ ಕಾಯ್ದುಕೊಂಡು ತುರ್ತು ವಾಹನಗಳಿಗೆ ದಾರಿ ಬಿಡಿ."),
        "breakdown": ("ವಾಹನ ಕೆಟ್ಟು ನಿಂತಿದೆ", "{place} ಬಳಿ ವಾಹನ ಕೆಟ್ಟು ನಿಂತಿದೆ. ಎಚ್ಚರಿಕೆಯಿಂದ ಹಾದುಹೋಗಿ; ಸುರಕ್ಷಿತವಾಗಿದ್ದರೆ ಮಾತ್ರ ಸಹಾಯ ಮಾಡಿ."),
        "fire": ("ಬೆಂಕಿ ಅವಘಡ", "{place} ಬಳಿ ಬೆಂಕಿ ಅವಘಡ ಸಂಭವಿಸಿದೆ. ಆ ಪ್ರದೇಶದಿಂದ ದೂರವಿರಿ ಮತ್ತು ಅಗತ್ಯವಿದ್ದರೆ ತುರ್ತು ಸೇವೆಗಳನ್ನು ಸಂಪರ್ಕಿಸಿ."),
        "medical": ("ವೈದ್ಯಕೀಯ ತುರ್ತು ಪರಿಸ್ಥಿತಿ", "{place} ಬಳಿ ವೈದ್ಯಕೀಯ ತುರ್ತು ಪರಿಸ್ಥಿತಿ ಇದೆ. ರಕ್ಷಣಾ ಸಿಬ್ಬಂದಿಗೆ ದಾರಿ ನೀಡಿ; ಸುರಕ್ಷಿತವಾಗಿದ್ದರೆ ಮಾತ್ರ ಸಹಾಯ ಮಾಡಿ."),
        "roadblock": ("ರಸ್ತೆ ತಡೆ", "{place} ಬಳಿ ರಸ್ತೆ ತಡೆ ಇದೆ. ವೇಗ ಕಡಿಮೆ ಮಾಡಿ ಮತ್ತು ಪರ್ಯಾಯ ಮಾರ್ಗವನ್ನು ಬಳಸಿ."),
        "vehicle": ("ವಾಹನದ ರಸ್ತೆ ಎಚ್ಚರಿಕೆ", "{place} ಬಳಿ ರಸ್ತೆ ಅಪಾಯ ವರದಿಯಾಗಿದೆ. ಸೂಚಿಸಿದ ವಾಹನದ ಚಾಲಕರು ವೇಗ ಕಡಿಮೆ ಮಾಡಿ ಎಚ್ಚರಿಕೆಯಿಂದ ಚಲಿಸಿ."),
        "other": ("ಸಮುದಾಯ ತುರ್ತು ಪರಿಸ್ಥಿತಿ", "{place} ಬಳಿ ತುರ್ತು ಪರಿಸ್ಥಿತಿ ವರದಿಯಾಗಿದೆ. ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ ಮತ್ತು ರಕ್ಷಣಾ ಸಿಬ್ಬಂದಿಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ."),
    },
    "ml": {
        "accident": ("റോഡ് അപകടം", "{place} സമീപം റോഡ് അപകടം റിപ്പോർട്ട് ചെയ്തിട്ടുണ്ട്. വേഗം കുറച്ച് സുരക്ഷിത അകലം പാലിക്കുകയും അടിയന്തര വാഹനങ്ങൾക്ക് വഴി നൽകുകയും ചെയ്യുക."),
        "breakdown": ("വാഹനം തകരാറിലായി", "{place} സമീപം ഒരു വാഹനം തകരാറിലായിട്ടുണ്ട്. ശ്രദ്ധയോടെ കടന്നുപോകുക; സുരക്ഷിതമാണെങ്കിൽ മാത്രം സഹായിക്കുക."),
        "fire": ("തീപിടിത്തം", "{place} സമീപം തീപിടിത്തം റിപ്പോർട്ട് ചെയ്തിട്ടുണ്ട്. പ്രദേശത്തുനിന്ന് മാറിനിൽക്കുകയും ആവശ്യമെങ്കിൽ അടിയന്തര സേവനങ്ങളെ ബന്ധപ്പെടുകയും ചെയ്യുക."),
        "medical": ("വൈദ്യ അടിയന്തരാവസ്ഥ", "{place} സമീപം വൈദ്യ അടിയന്തരാവസ്ഥ റിപ്പോർട്ട് ചെയ്തിട്ടുണ്ട്. രക്ഷാപ്രവർത്തകർക്ക് ഇടം നൽകുക; സുരക്ഷിതമാണെങ്കിൽ മാത്രം സഹായിക്കുക."),
        "roadblock": ("റോഡ് തടസ്സം", "{place} സമീപം റോഡ് തടസ്സമുണ്ട്. വേഗം കുറച്ച് മറ്റൊരു വഴി തിരഞ്ഞെടുക്കുക."),
        "vehicle": ("വാഹനത്തിനുള്ള റോഡ് മുന്നറിയിപ്പ്", "{place} സമീപം റോഡ് അപകടം റിപ്പോർട്ട് ചെയ്തിട്ടുണ്ട്. അറിയിച്ച വാഹനത്തിന്റെ ഡ്രൈവർമാർ വേഗം കുറച്ച് ജാഗ്രത പാലിക്കുക."),
        "other": ("സമൂഹ അടിയന്തരാവസ്ഥ", "{place} സമീപം അടിയന്തരാവസ്ഥ റിപ്പോർട്ട് ചെയ്തിട്ടുണ്ട്. ജാഗ്രത പാലിക്കുകയും രക്ഷാപ്രവർത്തകരുടെ നിർദ്ദേശങ്ങൾ പിന്തുടരുകയും ചെയ്യുക."),
    },
    "pa": {
        "accident": ("ਸੜਕ ਹਾਦਸਾ", "{place} ਨੇੜੇ ਸੜਕ ਹਾਦਸੇ ਦੀ ਸੂਚਨਾ ਮਿਲੀ ਹੈ। ਰਫ਼ਤਾਰ ਘਟਾਓ, ਸੁਰੱਖਿਅਤ ਦੂਰੀ ਰੱਖੋ ਅਤੇ ਐਮਰਜੈਂਸੀ ਵਾਹਨਾਂ ਨੂੰ ਰਸਤਾ ਦਿਓ।"),
        "breakdown": ("ਵਾਹਨ ਖ਼ਰਾਬ", "{place} ਨੇੜੇ ਇੱਕ ਵਾਹਨ ਖ਼ਰਾਬ ਹੋ ਗਿਆ ਹੈ। ਧਿਆਨ ਨਾਲ ਲੰਘੋ ਅਤੇ ਸੁਰੱਖਿਅਤ ਹੋਣ 'ਤੇ ਹੀ ਮਦਦ ਕਰੋ।"),
        "fire": ("ਅੱਗ ਦੀ ਸੂਚਨਾ", "{place} ਨੇੜੇ ਅੱਗ ਲੱਗਣ ਦੀ ਸੂਚਨਾ ਮਿਲੀ ਹੈ। ਇਲਾਕੇ ਤੋਂ ਦੂਰ ਰਹੋ ਅਤੇ ਲੋੜ ਪੈਣ 'ਤੇ ਐਮਰਜੈਂਸੀ ਸੇਵਾਵਾਂ ਨਾਲ ਸੰਪਰਕ ਕਰੋ।"),
        "medical": ("ਮੈਡੀਕਲ ਐਮਰਜੈਂਸੀ", "{place} ਨੇੜੇ ਮੈਡੀਕਲ ਐਮਰਜੈਂਸੀ ਹੈ। ਬਚਾਅ ਕਰਮਚਾਰੀਆਂ ਨੂੰ ਜਗ੍ਹਾ ਦਿਓ ਅਤੇ ਸੁਰੱਖਿਅਤ ਹੋਣ 'ਤੇ ਹੀ ਮਦਦ ਕਰੋ।"),
        "roadblock": ("ਸੜਕ ਬੰਦ", "{place} ਨੇੜੇ ਸੜਕ ਬੰਦ ਹੈ। ਰਫ਼ਤਾਰ ਘਟਾਓ ਅਤੇ ਬਦਲਵਾਂ ਰਸਤਾ ਚੁਣੋ।"),
        "vehicle": ("ਵਾਹਨ ਲਈ ਸੜਕ ਚੇਤਾਵਨੀ", "{place} ਨੇੜੇ ਸੜਕ ਦੇ ਖ਼ਤਰੇ ਦੀ ਸੂਚਨਾ ਮਿਲੀ ਹੈ। ਦੱਸੇ ਗਏ ਵਾਹਨ ਦੇ ਚਾਲਕ ਰਫ਼ਤਾਰ ਘਟਾ ਕੇ ਸਾਵਧਾਨੀ ਨਾਲ ਚੱਲਣ।"),
        "other": ("ਭਾਈਚਾਰਕ ਐਮਰਜੈਂਸੀ", "{place} ਨੇੜੇ ਐਮਰਜੈਂਸੀ ਦੀ ਸੂਚਨਾ ਮਿਲੀ ਹੈ। ਸਾਵਧਾਨ ਰਹੋ ਅਤੇ ਬਚਾਅ ਕਰਮਚਾਰੀਆਂ ਦੀਆਂ ਹਦਾਇਤਾਂ ਮੰਨੋ।"),
    },
    "ur": {
        "accident": ("سڑک حادثہ", "{place} کے قریب سڑک حادثے کی اطلاع ملی ہے۔ رفتار کم کریں، محفوظ فاصلہ رکھیں اور ہنگامی گاڑیوں کو راستہ دیں۔"),
        "breakdown": ("گاڑی خراب", "{place} کے قریب ایک گاڑی خراب ہو گئی ہے۔ احتیاط سے گزریں اور صرف محفوظ ہونے پر مدد کریں۔"),
        "fire": ("آگ لگنے کی اطلاع", "{place} کے قریب آگ لگنے کی اطلاع ملی ہے۔ علاقے سے دور رہیں اور ضرورت پڑنے پر ہنگامی خدمات سے رابطہ کریں۔"),
        "medical": ("طبی ہنگامی صورتحال", "{place} کے قریب طبی ہنگامی صورتحال ہے۔ امدادی کارکنوں کو جگہ دیں اور صرف محفوظ ہونے پر مدد کریں۔"),
        "roadblock": ("سڑک بند", "{place} کے قریب سڑک بند ہے۔ رفتار کم کریں اور متبادل راستہ اختیار کریں۔"),
        "vehicle": ("گاڑی کے لیے سڑک کی اطلاع", "{place} کے قریب سڑک پر خطرے کی اطلاع ہے۔ مطلع کردہ گاڑی کے ڈرائیور رفتار کم کریں اور احتیاط سے چلیں۔"),
        "other": ("عوامی ہنگامی صورتحال", "{place} کے قریب ہنگامی صورتحال کی اطلاع ملی ہے۔ چوکس رہیں اور امدادی کارکنوں کی ہدایات پر عمل کریں۔"),
    },
}

ALLOWED_CATEGORIES = set(TRANSLATIONS["en"])
VEHICLE_TYPES = {"car", "bike", "lorry"}
VEHICLE_LABELS = {
    "en": {"car": "cars", "bike": "bikes", "lorry": "lorries"},
    "hi": {"car": "कार", "bike": "बाइक", "lorry": "लॉरी"},
    "ta": {"car": "கார்கள்", "bike": "இருசக்கர வாகனங்கள்", "lorry": "லாரிகள்"},
    "te": {"car": "కార్లు", "bike": "బైక్‌లు", "lorry": "లారీలు"},
    "bn": {"car": "গাড়ি", "bike": "বাইক", "lorry": "লরি"},
    "mr": {"car": "कार", "bike": "दुचाकी", "lorry": "लॉरी"},
    "gu": {"car": "કાર", "bike": "બાઈક", "lorry": "લૉરી"},
    "kn": {"car": "ಕಾರುಗಳು", "bike": "ದ್ವಿಚಕ್ರ ವಾಹನಗಳು", "lorry": "ಲಾರಿಗಳು"},
    "ml": {"car": "കാറുകൾ", "bike": "ബൈക്കുകൾ", "lorry": "ലോറികൾ"},
    "pa": {"car": "ਕਾਰਾਂ", "bike": "ਮੋਟਰਸਾਈਕਲਾਂ", "lorry": "ਲਾਰੀਆਂ"},
    "ur": {"car": "کاریں", "bike": "موٹر سائیکلیں", "lorry": "لاریاں"},
}
lock = threading.RLock()
client_queues: dict[str, set[queue.Queue]] = {}


def load_state():
    if not STATE_FILE.exists():
        return {"profiles": {}, "subscriptions": {}, "alerts": [], "emergency_incidents": []}
    with STATE_FILE.open("r", encoding="utf-8") as file:
        state = json.load(file)
    if not all(key in state for key in ("profiles", "subscriptions", "alerts")):
        raise RuntimeError(f"Invalid state file: {STATE_FILE}")
    state.setdefault("emergency_incidents", [])
    return state


state = load_state()


def save_state():
    temporary = STATE_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
    temporary.replace(STATE_FILE)


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def distance_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    value = min(1.0, max(0.0, value))
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def locale_messages(locale, category, place, target_vehicle="all"):
    language = (locale or "en").replace("_", "-").split("-")[0].lower()
    catalog = TRANSLATIONS.get(language)
    if not catalog:
        language = "en"
        catalog = TRANSLATIONS[language]
    title, template = catalog.get(category, catalog["other"])
    if category == "vehicle" and target_vehicle in VEHICLE_TYPES:
        title = f"{title} · {VEHICLE_LABELS[language][target_vehicle]}"
    return {"title": title, "message": template.format(place=place or "nearby"), "language": language}


def profile_is_near(profile, alert):
    try:
        if profile.get("latitude") is None or profile.get("longitude") is None:
            return False
        return distance_km(
            float(profile["latitude"]),
            float(profile["longitude"]),
            alert["latitude"],
            alert["longitude"],
        ) <= alert["radius_km"]
    except (TypeError, ValueError):
        return False


def vehicle_matches(profile, alert):
    target = alert.get("target_vehicle", "all")
    return target == "all" or profile.get("vehicle_type") == target


def normalize_phone_number(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.fullmatch(r"\+[1-9][0-9\s().-]{5,23}", raw):
        raise ValueError("Enter a mobile number with country code, such as +91 98765 43210")
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        raise ValueError("Mobile number must contain 7 to 15 digits, including its country code")
    return f"+{digits}"


def alert_visible_to(client_id, profile, alert):
    if client_id == alert["reporter_id"]:
        return True
    target_client_ids = alert.get("target_client_ids")
    if target_client_ids is not None:
        return client_id in target_client_ids
    return profile_is_near(profile, alert) and vehicle_matches(profile, alert)


def public_alert(alert):
    return {key: value for key, value in alert.items() if key != "target_client_ids"}


def localized_alert_for(profile, alert):
    localized = locale_messages(
        profile.get("locale"), alert["category"], alert.get("place"), alert.get("target_vehicle", "all")
    )
    if alert.get("target_client_ids") is not None:
        localized["message"] = alert["message"]
    return {**public_alert(alert), **localized}


def publish_alert(alert):
    with lock:
        recipients = [
            (client_id, dict(profile))
            for client_id, profile in state["profiles"].items()
            if (
                client_id != alert["reporter_id"]
                and alert_visible_to(client_id, profile, alert)
            )
        ]
        subscriptions = {
            client_id: list(state["subscriptions"].get(client_id, []))
            for client_id, _ in recipients
        }

    delivered = 0
    push_sent = 0
    push_errors = 0
    for client_id, profile in recipients:
        envelope = localized_alert_for(profile, alert)
        localized = {"title": envelope["title"], "message": envelope["message"]}
        with lock:
            for recipient_queue in list(client_queues.get(client_id, set())):
                recipient_queue.put(("alert", envelope))
                delivered += 1

        if webpush and os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY"):
            for subscription in subscriptions.get(client_id, []):
                try:
                    webpush(
                        subscription_info=subscription,
                        data=json.dumps({
                            "title": localized["title"],
                            "body": localized["message"],
                            "url": "/",
                            "priority": alert["priority"],
                            "alert_id": alert["id"],
                            "target_vehicle": alert.get("target_vehicle", "all"),
                        }),
                        vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                        vapid_claims={"sub": os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@example.invalid")},
                    )
                    push_sent += 1
                except WebPushException as error:
                    push_errors += 1
                    print(f"Web Push delivery failed for client {client_id}: {error}", file=sys.stderr)
                    if getattr(getattr(error, "response", None), "status_code", None) in (404, 410):
                        with lock:
                            current = state["subscriptions"].get(client_id, [])
                            state["subscriptions"][client_id] = [
                                item for item in current if item.get("endpoint") != subscription.get("endpoint")
                            ]
                except (OSError, ValueError) as error:
                    push_errors += 1
                    print(f"Web Push delivery failed for client {client_id}: {error}", file=sys.stderr)

    if push_errors:
        with lock:
            save_state()
    return {
        "nearby_recipients": len(recipients),
        "recipient_count": len(recipients),
        "live_deliveries": delivered,
        "push_sent": push_sent,
        "push_errors": push_errors,
    }


def publish_alert_update(alert):
    with lock:
        recipients = [
            (client_id, dict(profile))
            for client_id, profile in state["profiles"].items()
            if alert_visible_to(client_id, profile, alert)
        ]
    for client_id, profile in recipients:
        envelope = localized_alert_for(profile, alert)
        with lock:
            for recipient_queue in list(client_queues.get(client_id, set())):
                recipient_queue.put(("alert-update", envelope))


class SmartAlertHandler(BaseHTTPRequestHandler):
    server_version = "SmartAlert/1.0"
    protocol_version = "HTTP/1.1"

    def send_json(self, status, data):
        body = json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.close_connection = True
            raise ValueError("Invalid Content-Length")
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            raise ValueError("Request body must be between 1 and 32000 bytes")
        if length < 1:
            raise ValueError("Request body must be between 1 and 32000 bytes")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise ValueError("Request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(200, {
                "status": "ok",
                "push_configured": bool(webpush and os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY")),
            })
            return
        if parsed.path == "/api/bootstrap":
            client_id = parse_qs(parsed.query).get("client_id", [""])[0]
            with lock:
                profile = state["profiles"].get(client_id)
                alerts = []
                if profile:
                    for item in reversed(state["alerts"][-MAX_ALERTS:]):
                        if not alert_visible_to(client_id, profile, item):
                            continue
                        alerts.append(localized_alert_for(profile, item))
                        if len(alerts) == 60:
                            break
            self.send_json(200, {"alerts": alerts, "supported_languages": sorted(TRANSLATIONS)})
            return
        if parsed.path == "/api/nearby":
            client_id = parse_qs(parsed.query).get("client_id", [""])[0]
            with lock:
                center = state["profiles"].get(client_id)
                volunteers = []
                if center:
                    for other_id, profile in state["profiles"].items():
                        if (
                            other_id != client_id
                            and profile.get("role") in ("volunteer", "responder")
                            and other_id in client_queues
                            and profile_is_near(profile, {
                                "latitude": center["latitude"],
                                "longitude": center["longitude"],
                                "radius_km": center["radius_km"],
                            })
                        ):
                            volunteers.append({
                                "name": profile["name"],
                                "role": profile["role"],
                                "distance_km": round(distance_km(
                                    center["latitude"],
                                    center["longitude"],
                                    profile["latitude"],
                                    profile["longitude"],
                                ), 1),
                            })
                volunteers.sort(key=lambda item: item["distance_km"])
            self.send_json(200, {"volunteers": volunteers})
            return
        if parsed.path == "/api/push/vapid-public-key":
            self.send_json(200, {"public_key": os.environ.get("VAPID_PUBLIC_KEY", "")})
            return
        if parsed.path == "/api/events":
            self.stream_events(parse_qs(parsed.query).get("client_id", [""])[0])
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()
            if path == "/api/profile":
                self.save_profile(data)
            elif path == "/api/alerts":
                self.create_alert(data)
            elif path == "/api/emergency/sos":
                self.create_emergency_sos(data)
            elif path == "/api/push/subscribe":
                self.save_subscription(data)
            elif path.startswith("/api/alerts/") and path.endswith("/verify"):
                self.verify_alert(unquote(path[len("/api/alerts/"):-len("/verify")]), data)
            else:
                self.send_json(404, {"error": "Not found"})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})

    def create_emergency_sos(self, data):
        client_id = str(data.get("client_id", ""))
        request_id = str(data.get("request_id", ""))
        if not client_id or len(client_id) > 80:
            raise ValueError("A valid enrolled profile is required")
        try:
            request_id = str(uuid.UUID(request_id))
        except (ValueError, AttributeError):
            raise ValueError("A valid SOS request id is required")
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("A current location is required to send an SOS")
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180")

        with lock:
            reporter = state["profiles"].get(client_id)
            if not reporter:
                raise ValueError("Enroll this device before sending an SOS")
            previous = next(
                (item for item in state["emergency_incidents"]
                 if item["client_id"] == client_id and item["request_id"] == request_id),
                None,
            )
            if previous:
                self.send_json(200, {
                    "incident": previous,
                    "delivery": previous["delivery"],
                    "dispatch_status": "demo_only",
                })
                return

        place = reporter.get("place") or f"{latitude:.4f}, {longitude:.4f}"
        alert = {
            "id": request_id,
            "category": "medical",
            "priority": "critical",
            "target_vehicle": "all",
            "place": place,
            "details": "One-touch SOS from the SmartAlert demo app.",
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": min(25.0, float(reporter.get("radius_km", 10))),
            "reporter_id": client_id,
            "reporter_name": reporter["name"],
            "status": "unverified",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        alert.update(locale_messages(reporter.get("locale"), alert["category"], place))
        with lock:
            state["alerts"].append(alert)
            state["alerts"] = state["alerts"][-MAX_ALERTS:]
            save_state()
        delivery = publish_alert(alert)
        incident = {
            "request_id": request_id,
            "client_id": client_id,
            "reporter_name": reporter["name"],
            "latitude": latitude,
            "longitude": longitude,
            "place": place,
            "created_at": alert["created_at"],
            "status": "demo_only",
            "delivery": delivery,
        }
        with lock:
            state["emergency_incidents"].append(incident)
            state["emergency_incidents"] = state["emergency_incidents"][-MAX_EMERGENCY_INCIDENTS:]
            save_state()
        print(
            f"DEMO SOS incident {request_id} recorded; "
            "no emergency service or hospital was contacted.",
            file=sys.stderr,
        )
        self.send_json(201, {
            "incident": incident,
            "delivery": delivery,
            "dispatch_status": "demo_only",
            "dispatch_message": "Recorded in the local demo log only. No emergency service or hospital was contacted.",
        })

    def save_profile(self, data):
        client_id = str(data.get("client_id", ""))
        if not client_id or len(client_id) > 80:
            raise ValueError("A valid client_id is required")
        name = str(data.get("name", "Neighbor")).strip()[:60] or "Neighbor"
        role = str(data.get("role", "resident"))
        if role not in ("resident", "driver", "volunteer", "responder"):
            raise ValueError("Invalid role")
        vehicle_type = str(data.get("vehicle_type", ""))
        if vehicle_type not in VEHICLE_TYPES and vehicle_type != "":
            raise ValueError("Vehicle type must be car, bike, lorry, or not specified")
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
            radius = float(data.get("radius_km", 10))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Valid latitude and longitude are required")
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        if not math.isfinite(radius) or not 1 <= radius <= 100:
            raise ValueError("Alert radius must be between 1 and 100 km")
        phone_alerts_enabled = data.get("phone_alerts_enabled") is True
        phone_number = normalize_phone_number(data.get("phone_number")) if phone_alerts_enabled else ""
        if phone_alerts_enabled and not phone_number:
            raise ValueError("Enter a mobile number before enabling direct alerts")
        profile = {
            "client_id": client_id,
            "name": name,
            "role": role,
            "vehicle_type": vehicle_type,
            "phone_number": phone_number,
            "phone_alerts_enabled": phone_alerts_enabled,
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius,
            "locale": str(data.get("locale", "en"))[:20],
            "place": str(data.get("place") or "").strip()[:100],
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with lock:
            state["profiles"][client_id] = profile
            save_state()
        self.send_json(200, {"profile": profile})

    def create_alert(self, data):
        category = str(data.get("category", ""))
        if category not in ALLOWED_CATEGORIES:
            raise ValueError("Choose a supported emergency category")
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
            radius = float(data.get("radius_km", 10))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Valid latitude and longitude are required")
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        if not math.isfinite(radius) or not 1 <= radius <= 25:
            raise ValueError("Alert radius must be between 1 and 25 km")
        priority = str(data.get("priority", "high"))
        if priority not in ("critical", "high", "normal"):
            raise ValueError("Invalid priority")
        target_vehicle = str(data.get("target_vehicle", "all"))
        if target_vehicle not in VEHICLE_TYPES and target_vehicle != "all":
            raise ValueError("Choose cars, bikes, lorries, or all vehicle types")
        if category != "vehicle":
            target_vehicle = "all"
        recipient_phone = normalize_phone_number(data.get("recipient_phone"))
        custom_message = str(data.get("custom_message", "")).strip()
        if len(custom_message) > 500:
            raise ValueError("Custom alert message must be 500 characters or fewer")
        target_client_ids = None
        with lock:
            reporter = state["profiles"].get(str(data.get("reporter_id", "")))
            if recipient_phone:
                target_client_ids = [
                    client_id
                    for client_id, profile in state["profiles"].items()
                    if client_id != str(data.get("reporter_id", ""))
                    and profile.get("phone_alerts_enabled") is True
                    and profile.get("phone_number") == recipient_phone
                ]
        if not reporter:
            raise ValueError("Save your profile before reporting an alert")
        if recipient_phone:
            if not custom_message:
                raise ValueError("Add a custom message for the mobile-number recipient")
            if not target_client_ids:
                raise ValueError("No registered profile with direct mobile alerts is using that number")
        place = str(data.get("place") or "").strip()[:100] or f"{latitude:.4f}, {longitude:.4f}"
        alert = {
            "id": str(uuid.uuid4()),
            "category": category,
            "priority": priority,
            "target_vehicle": target_vehicle,
            "place": place,
            "details": str(data.get("details", "")).strip()[:300],
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius,
            "reporter_id": reporter["client_id"],
            "reporter_name": reporter["name"],
            "status": "unverified",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if target_client_ids is not None:
            alert["target_client_ids"] = target_client_ids
        localized = locale_messages(reporter.get("locale"), category, place, target_vehicle)
        alert.update(localized)
        if recipient_phone:
            alert["message"] = custom_message
        with lock:
            state["alerts"].append(alert)
            state["alerts"] = state["alerts"][-MAX_ALERTS:]
            save_state()
        delivery = publish_alert(alert)
        self.send_json(201, {"alert": public_alert(alert), "delivery": delivery})

    def save_subscription(self, data):
        client_id = str(data.get("client_id", ""))
        subscription = data.get("subscription")
        if not client_id or len(client_id) > 80 or not isinstance(subscription, dict):
            raise ValueError("A client_id and valid push subscription are required")
        endpoint = subscription.get("endpoint", "")
        keys = subscription.get("keys")
        if not isinstance(endpoint, str) or len(endpoint) > 4096 or not endpoint.startswith("https://"):
            raise ValueError("Push subscription endpoint must use HTTPS")
        if not isinstance(keys, dict) or not all(isinstance(keys.get(key), str) and keys[key] for key in ("p256dh", "auth")):
            raise ValueError("Push subscription must include valid encryption keys")
        with lock:
            if client_id not in state["profiles"]:
                raise ValueError("Save your profile before enabling push notifications")
            current = state["subscriptions"].setdefault(client_id, [])
            current[:] = [item for item in current if item.get("endpoint") != subscription["endpoint"]]
            current.append(subscription)
            save_state()
        self.send_json(201, {"enabled": True})

    def verify_alert(self, alert_id, data):
        if not alert_id:
            raise ValueError("Alert id is required")
        with lock:
            alert = next((item for item in state["alerts"] if item["id"] == alert_id), None)
            if not alert:
                self.send_json(404, {"error": "Alert not found"})
                return
            alert["status"] = "verified" if data.get("verified") else "unverified"
            updated_alert = dict(alert)
            save_state()
            profile = state["profiles"].get(str(data.get("client_id", "")))
        publish_alert_update(updated_alert)
        localized = locale_messages(
            profile.get("locale") if profile else "en",
            updated_alert["category"],
            updated_alert.get("place"),
            updated_alert.get("target_vehicle", "all"),
        )
        response_alert = {**public_alert(updated_alert), **localized}
        if updated_alert.get("target_client_ids") is not None:
            response_alert["message"] = updated_alert["message"]
        self.send_json(200, {"alert": response_alert})

    def stream_events(self, client_id):
        if not client_id or len(client_id) > 80:
            self.send_json(400, {"error": "A valid client_id is required"})
            return
        with lock:
            if client_id not in state["profiles"]:
                self.send_json(404, {"error": "Save a profile before opening a live connection"})
                return
        recipient_queue = queue.Queue()
        with lock:
            client_queues.setdefault(client_id, set()).add(recipient_queue)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b": SmartAlert connection ready\n\n")
            self.wfile.flush()
            while True:
                try:
                    event_name, item = recipient_queue.get(timeout=20)
                    payload = json_bytes(item)
                    self.wfile.write(f"event: {event_name}\ndata: ".encode("ascii") + payload + b"\n\n")
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            with lock:
                queues = client_queues.get(client_id)
                if queues:
                    queues.discard(recipient_queue)
                    if not queues:
                        client_queues.pop(client_id, None)

    def serve_static(self, path):
        relative = "index.html" if path in ("", "/") else unquote(path.lstrip("/"))
        target = (PUBLIC / relative).resolve()
        if not target.is_relative_to(PUBLIC.resolve()) or not target.is_file():
            self.send_json(404, {"error": "Not found"})
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(target.suffix.lower(), "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), format_string % args))


if __name__ == "__main__":
    print(f"SmartAlert listening on http://{HOST}:{PORT}")
    if not webpush:
        print("Web Push is unavailable. Install requirements.txt to enable it.")
    elif not os.environ.get("VAPID_PRIVATE_KEY") or not os.environ.get("VAPID_PUBLIC_KEY"):
        print("Web Push is not configured. Set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY.")
    ThreadingHTTPServer((HOST, PORT), SmartAlertHandler).serve_forever()
