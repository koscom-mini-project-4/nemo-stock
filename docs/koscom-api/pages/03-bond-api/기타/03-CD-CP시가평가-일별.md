# CD/CP시가평가-일별

- category: 채권-API
- group: 기타
- url: https://checkapi.koscom.co.kr/cdcp_hist

---

[CD/CP시가평가 일별]
● Request
URL

    HOST https://checkapi.koscom.co.kr
    POST /bond/etc/cdcp_hist
  
Parameter
Name	Type	Description	Required
cust_id	String	CHECK 단말 고객번호 10자리 (ex : NS00000001)	O
auth_key	String	API 인증키	O
jcode	String	종목코드 11자리 (ex : 07213300270)	O
		시가평가사기관코드(2자리) + CPCD구분코드(1자리) + 신용평가코드(3자리) + 잔존만기일수(5자리)	
sdate	String	시작일자 (ex : 20230201)	O
edate	String	종료일자 (ex : 20230228)	O
Data Set
Name	Type	Description	Detail
F12506	NUMERIC(8)	일자	
F16013	CHAR(12)	종목코드	
F34735	NUMERIC(1)	CPCD구분코드	(1:CD,2:CP)
F34711	NUMERIC(3)	신용평가코드	
F34339	NUMERIC(5)	잔존만기일수	
F16347	NUMERIC(2)	시가평가사기관코드	(1:NICE,2:KIS,3:KAP,5:FN,6:3사,7:4사)
F15175	NUMERIC(8,5)	수익율	
F34904	NUMERIC(4)	시가평가기관수	

API 테스트 도구
outlink

Example

    python 
    
      import sys, json, requests

      session = requests.Session()
      # SSL 인증 처리 무효화 
      session.verify = False
      host_url = 'https://checkapi.koscom.co.kr'
      api_url = '/bond/etc/cdcp_hist'
      # sample parameter 입니다. 정상 처리 되지 않습니다.
      payload = {
        "cust_id" : "NS00000001",
        "auth_key" : "Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj",
        "data_list" : "F16013, F15001",
        "jcode" : ""
      }
      r = session.post(host_url + api_url, data = payload)

      # 정렬. ensure_ascii = 한글 깨짐 방지. indent = 들여쓰기.
      print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    
  
, { "key": "jcode" }

    javascript 
    
      axios.post('https://checkapi.koscom.co.kr/bond/etc/cdcp_hist',
        // sample parameter 입니다. 정상 처리 되지 않습니다.
        {
          cust_id : "NS00000001",
          auth_key : "Y0va9PYmoKiqWJ7oSVFiyIy2aVHq7lXj",
          data_list : "F16013, F15001",
          jcode : ""
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
    
  
