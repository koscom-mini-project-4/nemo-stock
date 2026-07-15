# FRN-상세

- category: 채권-API
- group: 채권발행정보
- url: https://checkapi.koscom.co.kr/bond/m058hfrnrefe

---

[FRN-상세]
● Request
URL

    HOST https://checkapi.koscom.co.kr
    POST /bond/m058/m058hfrnrefe
  
Parameter
Name	Type	Description	Required
cust_id	String	CHECK 단말 고객번호 10자리 (ex : NS00000001)	O
auth_key	String	API 인증키	O
jcode	String	종목코드 12자리 (ex : KR101701DA22)	O
Data Set
Name	Type	Description	Detail
F16013	CHAR(12)	종목코드	
FRN_TYPE	NUMERIC(2)	FRN유형	
REF_RATE_1	VARCHAR(20)	기초자산금리1	
REF_RATE_2	VARCHAR(20)	기초자산금리2	
REF_RATE_3	VARCHAR(20)	기초자산금리3	
REF_RATE_4	VARCHAR(20)	기초자산금리4	
REF_RATE_5	VARCHAR(20)	기초자산금리5	
FRN_SPEC	VARCHAR(4000)	FRN조건상세	
LOOKBACK	NUMERIC(2)	Lookback(Days)	
ROUNDING	NUMERIC(2)	Rounding	
ROUNDING_RULE	VARCHAR(40)	Rounding Rule	
FLOOR_RULE	VARCHAR(40)	Floor 적용방법	
FLOOR_RATE	VARCHAR(40)	Floor 금리	
HOL_LOC	CHAR(3)	휴일적용지역	
RESET_TYPE	NUMERIC(2)	Reset Type	(1:In-advanced, 2:In-arrear, 3:MBS배당, 4:기간설정In-advanced)
FIXED_YEAR	NUMERIC(2)	Reset년수(Reset Type 4의 경우 적용)	

API 테스트 도구
outlink

Example

    python 
    
      import sys, json, requests

      session = requests.Session()
      # SSL 인증 처리 무효화 
      session.verify = False
      host_url = 'https://checkapi.koscom.co.kr'
      api_url = '/bond/m058/m058hfrnrefe'
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
    
      axios.post('https://checkapi.koscom.co.kr/bond/m058/m058hfrnrefe',
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
    
  
