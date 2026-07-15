# GAAP(code)

- category: 기타-API
- group: GAAP
- url: https://checkapi.koscom.co.kr/comp/compgaapcode

---

[GAAP 계정코드 일람]
● Request
URL

    HOST https://checkapi.koscom.co.kr
    POST /etc/gaap/comp_gaap_code
  
Parameter
Name	Type	Description	Required
cust_id	String	CHECK 단말 고객번호 10자리 (ex : NS00000001)	O
auth_key	String	API 인증키	O
Data Set
Name	Type	Description	Detail
ITEM_CD	CHAR(6)	계정코드	
FINACC_TYP	NUMERIC(2)	재무업종	0:전체,1:제조,2:은행,3:보험,
			4:증권,6:신용금고,7:종합금융,8:여신전문금융,9:기타금융)
ITEM_TYP	CHAR(1)	코드타입	A:재무제표,B:잉여현금흐름,C:재무비율,D:Valuation Ratios,M:공통계정
FS_TYP	CHAR(2)	재무제표종류	1:대차대조표,2:손익계산서,3:이익잉여금처분계산서,
			4:현금흐름표,5:제조원가명세서,6:자본변동표,9:잉여현금흐름표
			,10:재무비율,11:주당지표,12:배당,13:자기주식,
			19:Valuation Ratios,20:Commmon Ratios,99:기타
ITEM_NM_KOR	VARCHAR(200)	한글명	
ITEM_NM_ENG	VARCHAR(200)	영문명	
UNT_TYP	NUMERIC(3)	단위	2:천,6:%,8:배,12:천주,101:Text,102:구분,111:원/주,
			121:포인트,122:갯수

API 테스트 도구

outlink

Example

    python 
    
      import sys, json, requests

      session = requests.Session()
      # SSL 인증 처리 무효화 
      session.verify = False
      host_url = 'https://checkapi.koscom.co.kr'
      api_url = '/etc/gaap/comp_gaap_code'

      # sample parameter 입니다. 정상 처리 되지 않습니다.
      payload = {"cust_id" : 'NS00000001', "auth_key" : 'Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj'}
      r = session.post(host_url + api_url, data = payload)

      # 정렬. ensure_ascii = 한글 깨짐 방지. indent = 들여쓰기.
      print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    
  

    javascript 
    
      axios.post('https://checkapi.koscom.co.kr/etc/gaap/comp_gaap_code', 
        // sample parameter 입니다. 정상 처리 되지 않습니다.
        {"cust_id" : 'NS00000001', "auth_key" : 'Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj'}
      ).then(function(res) {
        if(res.data.success == true){
          // 정상 데이터 처리
          console.log(res.data.results);
        }else {
          // 에러 처리
          console.log(res.data.message);
        }
      });
    
  

    java
    * JAVA의 https 접속방식 복잡성으로 별도 EXAMPLE을 제공하지 않습니다.
    * 고객번호 / 인증키 유출위험으로 http 및 GET 서비스는 제공하지 않습니다.
  
● Response
Name	Value	Description	Detail
success	true	정상	results 참조
results	[Data Set]	-	-
success	false	비정상	message 참조
message	[Error Set]	-	-
Error Message
Error	Error Desc	Description
access_denied	User denied access	고객번호 또는 인증키가 유효하지 않습니다.
jcode_denied	Input code is not found	입력한 종목코드가 유효하지 않습니다.
Example

    json 
    
      {"success":false,
        "message": {errmsg : "access_denied", desc : "User denied access"}},
    
  
