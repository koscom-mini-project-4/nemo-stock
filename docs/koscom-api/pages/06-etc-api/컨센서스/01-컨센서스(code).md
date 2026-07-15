# 컨센서스(code)

- category: 기타-API
- group: 컨센서스
- url: https://checkapi.koscom.co.kr/comp/compconscode

---

[컨센서스 계정코드 일람]
● Request
URL

    HOST https://checkapi.koscom.co.kr
    POST /etc/cons/comp_cons_code
  
Parameter
Name	Type	Description	Required
cust_id	String	CHECK 단말 고객번호 10자리 (ex : NS00000001)	O
auth_key	String	API 인증키	O
Data Set
Name	Type	Description	Detail
ITEM_CD	CHAR(6)	계정코드	
FINACC_TYP	NUMERIC(2)	재무업종	0:전체
ITEM_TYP	CHAR(1)	코드타입	E:컨센서스
ITEM_NM_KOR	VARCHAR(200)	한글명	
ITEM_NM_ENG	VARCHAR(200)	영문명	
UNT_TYP	NUMERIC(3)	단위	(2:천,6:%,8:배,12:천주,101:Text,102:구분,111:원/주,
			121:포인트,122:갯수)
CMP_YN	NUMERIC(1)	기업 아이템여부	0:미사용,1:사용
SEC_YN	NUMERIC(1)	섹터 아이템여부	0:미사용,1:사용
CMS_TYP	NUMERIC(1)	섹터 아이템여부	1:재무계정,2:비재무계정

API 테스트 도구
outlink

Example

    python 
    
      import sys, json, requests

      session = requests.Session()
      # SSL 인증 처리 무효화 
      session.verify = False
      host_url = 'https://checkapi.koscom.co.kr'
      api_url = '/etc/cons/comp_cons_code'

      # sample parameter 입니다. 정상 처리 되지 않습니다.
      payload = {"cust_id" : 'NS00000001', "auth_key" : 'Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj'}
      r = session.post(host_url + api_url, data = payload)

      # 정렬. ensure_ascii = 한글 깨짐 방지. indent = 들여쓰기.
      print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    
  

    javascript 
    
      axios.post('https://checkapi.koscom.co.kr/etc/cons/comp_cons_code', 
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
    
  
