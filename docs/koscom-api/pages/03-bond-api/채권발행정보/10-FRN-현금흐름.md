# FRN-현금흐름

- category: 채권-API
- group: 채권발행정보
- url: https://checkapi.koscom.co.kr/bond/m058hfrncsfw

---

[FRN_현금흐름]
● Request
URL

    HOST https://checkapi.koscom.co.kr
    POST /bond/m058/m058hfrncsfw
  
Parameter
Name	Type	Description	Required
cust_id	String	CHECK 단말 고객번호 10자리 (ex : NS00000001)	O
auth_key	String	API 인증키	O
jcode	String	종목코드 12자리 (ex : KR101701DA22)	O
Data Set
Name	Type	Description	Detail
F16013	CHAR(12)	종목코드	
INT_DIV	NUMERIC(2)	원금이자구분(1:원금,2:이자)	
FIX_DIV	NUMERIC(2)	고정변동구분(0:고정,1:변동)	
RESET_DATE	NUMERIC(8)	이자결정일	
START_DATE	NUMERIC(8)	이자계산시작일	
END_DATE	NUMERIC(8)	이자계산종료일	
PAYMENT_DATE	NUMERIC(8)	이자지급일	
OB_RATE	NUMERIC(9,5)	관찰금리	
SPREAD	NUMERIC(9,5)	스프레드	
RATE	NUMERIC(9,5)	이자율	
CF	NUMERIC(32,20)	지급현금흐름	
REF_RATE_1	VARCHAR(20)	기초자산금리1	
REF_RATE_2	VARCHAR(20)	기초자산금리2	
F33867	NUMERIC(2)	입력구분코드	(0:정상,1:수입력)
F16455	NUMERIC(2)	이자율확정Bit	(0:확정아님,1:확정)
F34648	NUMERIC(30,28)	할인단위	
F34649	NUMERIC(4)	할인단위일수	
F34650	NUMERIC(4)	할인일수	

API 테스트 도구
outlink

Example

    python 
    
      import sys, json, requests

      session = requests.Session()
      # SSL 인증 처리 무효화 
      session.verify = False
      host_url = 'https://checkapi.koscom.co.kr'
      api_url = '/bond/m058/m058hfrncsfw'
      # sample parameter 입니다. 정상 처리 되지 않습니다.
      payload = {
        "cust_id" : "NS00000001",
        "auth_key" : "Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj",
        "data_list" : "F16013, F15001",
        "jcode" : "KR101701DA22"
      }
      r = session.post(host_url + api_url, data = payload)

      # 정렬. ensure_ascii = 한글 깨짐 방지. indent = 들여쓰기.
      print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    
  
, { "key": "jcode", "value": "KR101701DA22" }

    javascript 
    
      axios.post('https://checkapi.koscom.co.kr/bond/m058/m058hfrncsfw',
        // sample parameter 입니다. 정상 처리 되지 않습니다.
        {
          cust_id : "NS00000001",
          auth_key : "Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj",
          data_list : "F16013, F15001",
          jcode : "KR101701DA22"
        }
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
    
  
