    #pip3 install shapely
from flask import Flask, request, render_template, url_for, redirect
from flask_restful import Resource, Api
from flask_mail import Mail, Message  # used for email
# used for serializer email and error handling
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from flask_cors import CORS
import jwt
import boto3
from werkzeug.exceptions import BadRequest, NotFound

from dateutil.relativedelta import *
from decimal import Decimal
from datetime import datetime, date, timedelta
from hashlib import sha512
from math import ceil
import string
import random
#regex
import re
#from env_keys import BING_API_KEY, RDS_PW

import decimal
import sys
import json
import pytz
import pymysql
import requests
import stripe
import binascii
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import os
s3 = boto3.client('s3')

# RDS for AWS SQL 5.7
# RDS_HOST = 'pm-mysqldb.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
# RDS for AWS SQL 8.0
RDS_HOST = 'io-mysqldb8.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
RDS_PORT = 3306
RDS_USER = 'admin'
RDS_DB = 'M4ME'

app = Flask(__name__)
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
# Set this to false when deploying to live application
app.config['DEBUG'] = True
# Adding for email testing
#app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_SERVER'] = 'smtp.mydomain.com'
app.config['MAIL_PORT'] = 465

app.config['MAIL_USERNAME'] = 'support@mealsfor.me'
app.config['MAIL_PASSWORD'] = 'SupportM4Me'
app.config['MAIL_DEFAULT_SENDER'] = 'support@mealsfor.me'

# app.config['MAIL_USERNAME'] = os.environ.get('SUPPORT_EMAIL')
# app.config['MAIL_PASSWORD'] = os.environ.get('SUPPORT_PASSWORD')
# app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('SUPPORT_EMAIL')

RDS_PW = os.environ.get('RDS_PW')

RDS_PW="prashant"

app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
# app.config['MAIL_DEBUG'] = True
# app.config['MAIL_SUPPRESS_SEND'] = False
# app.config['TESTING'] = False
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
mail = Mail(app)
s = URLSafeTimedSerializer('thisisaverysecretkey')
# API
api = Api(app)

# convert to UTC time zone when testing in local time zone
utc = pytz.utc
def getToday(): return datetime.strftime(datetime.now(utc), "%Y-%m-%d")
def getNow(): return datetime.strftime(datetime.now(utc),"%Y-%m-%d %H:%M:%S")

# Connect to MySQL database (API v2)
def connect():
    global RDS_PW
    global RDS_HOST
    global RDS_PORT
    global RDS_USER
    global RDS_DB

    print("Trying to connect to RDS (API v2)...")
    try:
        conn = pymysql.connect(host=RDS_HOST,
                               user=RDS_USER,
                               port=RDS_PORT,
                               passwd=RDS_PW,
                               db=RDS_DB,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)
        print("Successfully connected to RDS. (API v2)")
        return conn
    except:
        print("Could not connect to RDS. (API v2)")
        raise Exception("RDS Connection failed. (API v2)")


# Disconnect from MySQL database (API v2)
def disconnect(conn):
    try:
        conn.close()
        print("Successfully disconnected from MySQL database. (API v2)")
    except:
        print("Could not properly disconnect from MySQL database. (API v2)")
        raise Exception("Failure disconnecting from MySQL database. (API v2)")




# Serialize JSON
def serializeResponse(response):
    # def is_json(myjson):
    #     try:
    #         if type(myjson) is not str:
    #             return False
    #         json.loads(myjson)
    #     except ValueError as e:
    #         return False
    #     return True
    try:
        for row in response:
            for key in row:
                if type(row[key]) is Decimal:
                    row[key] = float(row[key])
                elif (type(row[key]) is date or type(row[key]) is datetime) and row[key] is not None:
                # Change this back when finished testing to get only date
                    # row[key] = row[key].strftime("%Y-%m-%d")
                    row[key] = row[key].strftime("%Y-%m-%d %H-%M-%S")
                # elif is_json(row[key]):
                #     row[key] = json.loads(row[key])
                elif isinstance(row[key], bytes):
                    row[key] = row[key].decode()
        return response
    except:
        raise Exception("Bad query JSON")


# Execute an SQL command (API v2)
# Set cmd parameter to 'get' or 'post'
# Set conn parameter to connection object
# OPTIONAL: Set skipSerialization to True to skip default JSON response serialization
def execute(sql, cmd, conn, skipSerialization=False):
    response = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cmd == 'get':
                result = cur.fetchall()
                response['message'] = 'Successfully executed SQL query.'
                # Return status code of 280 for successful GET request
                response['code'] = 280
                if not skipSerialization:
                    result = serializeResponse(result)
                response['result'] = result
            elif cmd == 'post':
                conn.commit()
                response['message'] = 'Successfully committed SQL command.'
                # Return status code of 281 for successful POST request
                response['code'] = 281
            else:
                response['message'] = 'Request failed. Unknown or ambiguous instruction given for MySQL command.'
                # Return status code of 480 for unknown HTTP method
                response['code'] = 480
    except:
        response['message'] = 'Request failed, could not execute MySQL command.'
        # Return status code of 490 for unsuccessful HTTP request
        response['code'] = 490
    finally:
        # response['sql'] = sql
        return response

def get_new_paymentID(conn):
    newPaymentQuery = execute("CALL new_payment_uid", 'get', conn)
    if newPaymentQuery['code'] == 280:
        return newPaymentQuery['result'][0]['new_id']
    return "Could not generate new payment ID", 500

def get_new_purchaseID(conn):
    newPurchaseQuery = execute("CALL new_purchase_uid", 'get', conn)
    if newPurchaseQuery['code'] == 280:
        return newPurchaseQuery['result'][0]['new_id']
    return "Could not generate new purchase ID", 500

def get_new_id(query, name, conn):
    response = {}
    new_id = execute(query, 'get', conn)
    if new_id['code'] != 280:
        response['message'] = 'Could not generate ' + name + "."
        return response, 500
    response['message'] = "OK"
    response['result'] = new_id['result'][0]['new_id']
    return response, 200

def simple_get_execute(query, name_to_show, conn):
    response = {}
    res = execute(query, 'get', conn)
    if res['code'] != 280:
        search = re.search(r'#(.*?):', query)
        query_number = "    " + search.group(1) + "     " if search is not None else "UNKNOWN QUERY NUMBER"
        string = " Cannot run the query for " + name_to_show + "."
        print("\n")
        print("*" * (len(string) + 10))
        print(string.center(len(string) + 10, "*"))
        print(query_number.center(len(string) + 10, "*"))
        print("*" * (len(string) + 10), "\n")
        response['message'] = 'Internal Server Error.'
        return response, 500
    elif not res['result']:
        response['message'] = 'Can not found the requested info.'
        return response, 204
    else:
        response['message'] = "Get " + name_to_show + " successful."
        response['result'] = res['result']

        return response, 200

def simple_post_execute(queries, names, conn):
    response = {}
    if len(queries) != len(names):
        return "Error. Queries and Names should have the same length."
    for i in range(len(queries)):
        res = execute(queries[i], 'post', conn)
        if res['code'] != 281:
            string = " Cannot Insert into the " + names[i] + " table. "
            print("*" * (len(string) + 10))
            print(string.center(len(string) + 10, "*"))
            print("*" * (len(string) + 10))
            response['message'] = "Internal Server Error."
            return response, 500
    response['message'] = "Successful."
    return response, 201

def allowed_file(filename):
    """Checks if the file is allowed to upload"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def destructure (d, *keys):
    return [d[k] if k in d else None for k in keys]


def helper_upload_meal_img(file, key):
    bucket = 'mtyd'
    print("photo 1")
    if file and allowed_file(file.filename):
        filename = 'https://s3-us-west-1.amazonaws.com/' \
                    + str(bucket) + '/' + str(key)
        print("photo 2")
        upload_file = s3.put_object(
                            Bucket=bucket,
                            Body=file,
                            Key=key,
                            ACL='public-read',
                            ContentType='image/jpeg'
                        )
        return filename
    return None



paypal_secret_test_key = os.environ.get('paypal_secret_key_test')
paypal_secret_live_key = os.environ.get('paypal_secret_key_live')

paypal_client_test_key = os.environ.get('paypal_client_test_key')
paypal_client_live_key = os.environ.get('paypal_client_live_key')

stripe_public_test_key = os.environ.get('stripe_public_test_key')
stripe_secret_test_key = os.environ.get('stripe_secret_test_key')

stripe_public_live_key = os.environ.get('stripe_public_live_key')
stripe_secret_live_key = os.environ.get('stripe_secret_live_key')

#stripe.api_key = stripe_secret_test_key

#use below for local testing
#stripe.api_key = "sk_test_51HyqrgLMju5***Gkl299bo00yD1lTRNK"




def get_all_s3_keys(bucket):
    """Get a list of all keys in an S3 bucket."""
    print("list 2")
    keys = []
    print("list 1")
    kwargs = {'Bucket': "mtyd"}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp['Contents']:
            keys.append(obj['Key'])

        try:
            kwargs['ContinuationToken'] = resp['NextContinuationToken']
        except KeyError:
            break
    print(keys)
    return keys



#print("Key: ", paypal_secret_test_key)

# def helper_upload_meal_img(file, key):
#     bucket = 'servingfresh'
#     print("1")
#     #if file and allowed_file(file.filename):
#     filename = 'https://s3-us-west-1.amazonaws.com/' \
#                 + str(bucket) + '/' + str(key)
#     print(filename)
#     upload_file = s3.put_object(
#                         Bucket=bucket,
#                         Body=file,
#                         Key=key,
#                         ACL='public-read',
#                         ContentType='image/jpeg'
#                     )
#     return filename
#     return None



# class SignUp(Resource):
#     def post(self):
#         response = {}
#         items = []
#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             print(data)
#             email = data['email']
#             firstName = data['first_name']
#             lastName = data['last_name']
#             phone = data['phone_number']
#             address = data['address']
#             unit = data['unit'] if data.get('unit') is not None else 'NULL'
#             social_id = data['social_id'] if data.get('social_id') is not None else 'NULL'
#             city = data['city']
#             state = data['state']
#             zip_code = data['zip_code']
#             latitude = data['latitude']
#             longitude = data['longitude']
#             referral = data['referral_source']
#             role = data['role']
#             cust_id = data['cust_id'] if data.get('cust_id') is not None else 'NULL'

#             if data.get('social') is None or data.get('social') == "FALSE" or data.get('social') == False:
#                 social_signup = False
#             else:str
#                 social_signup = True

#             print(social_signup)
#             get_user_id_query = "CALL new_customer_uid();"
#             NewUserIDresponse = execute(get_user_id_query, 'get', conn)

#             if NewUserIDresponse['code'] == 490:
#                 string = " Cannot get new User id. "
#                 print("*" * (len(string) + 10))
#                 print(string.center(len(string) + 10, "*"))
#                 print("*" * (len(string) + 10))
#                 response['message'] = "Internal Server Error."
#                 return response, 500
#             NewUserID = NewUserIDresponse['result'][0]['new_id']

#             if social_signup == False:

#                 salt = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

#                 password = sha512((data['password'] + salt).encode()).hexdigest()
#                 print('password------', password)
#                 algorithm = "SHA512"
#                 mobile_access_token = 'NULL'
#                 mobile_refresh_token = 'NULL'
#                 user_access_token = 'NULL'
#                 user_refresh_token = 'NULL'
#                 user_social_signup = 'NULL'
#             else:

#                 mobile_access_token = data['mobile_access_token']
#                 mobile_refresh_token = data['mobile_refresh_token']
#                 user_access_token = data['user_access_token']
#                 user_refresh_token = data['user_refresh_token']
#                 salt = 'NULL'
#                 password = 'NULL'
#                 algorithm = 'NULL'
#                 user_social_signup = data['social']

#                 print('ELSE- OUT')

#             if cust_id != 'NULL' and cust_id:

#                 NewUserID = cust_id

#                 query = '''
#                             SELECT user_access_token, user_refresh_token, mobile_access_token, mobile_refresh_token 
#                             FROM M4ME.customers
#                             WHERE customer_uid = \'''' + cust_id + '''\';
#                        '''
#                 it = execute(query, 'get', conn)
#                 print('it-------', it)

#                 if it['result'][0]['user_access_token'] != 'FALSE':
#                     user_access_token = it['result'][0]['user_access_token']

#                 if it['result'][0]['user_refresh_token'] != 'FALSE':
#                     user_refresh_token = it['result'][0]['user_refresh_token']

#                 if it['result'][0]['mobile_access_token'] != 'FALSE':
#                     mobile_access_token = it['result'][0]['mobile_access_token']

#                 if it['result'][0]['mobile_refresh_token'] != 'FALSE':
#                     mobile_refresh_token = it['result'][0]['mobile_refresh_token']

#                 customer_insert_query =  ['''
#                                     UPDATE M4ME.customers 
#                                     SET 
#                                     customer_created_at = \'''' + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + '''\',
#                                     customer_first_name = \'''' + firstName + '''\',
#                                     customer_last_name = \'''' + lastName + '''\',
#                                     customer_phone_num = \'''' + phone + '''\',
#                                     customer_address = \'''' + address + '''\',
#                                     customer_unit = \'''' + unit + '''\',
#                                     customer_city = \'''' + city + '''\',
#                                     customer_state = \'''' + state + '''\',
#                                     customer_zip = \'''' + zip_code + '''\',
#                                     customer_lat = \'''' + latitude + '''\',
#                                     customer_long = \'''' + longitude + '''\',
#                                     password_salt = \'''' + salt + '''\',
#                                     password_hashed = \'''' + password + '''\',
#                                     password_algorithm = \'''' + algorithm + '''\',
#                                     referral_source = \'''' + referral + '''\',
#                                     role = \'''' + role + '''\',
#                                     user_social_media = \'''' + user_social_signup + '''\',
#                                     social_timestamp  =  DATE_ADD(now() , INTERVAL 14 DAY)
#                                     WHERE customer_uid = \'''' + cust_id + '''\';
#                                     ''']


#             else:

#                 # check if there is a same customer_id existing
#                 query = """
#                         SELECT customer_email FROM M4ME.customers
#                         WHERE customer_email = \'""" + email + "\';"
#                 print('email---------')
#                 items = execute(query, 'get', conn)
#                 if items['result']:

#                     items['result'] = ""
#                     items['code'] = 409
#                     items['message'] = "Email address has already been taken."

#                     return items

#                 if items['code'] == 480:

#                     items['result'] = ""
#                     items['code'] = 480
#                     items['message'] = "Internal Server Error."
#                     return items


#                 # write everything to database
#                 customer_insert_query = ["""
#                                         INSERT INTO M4ME.customers 
#                                         (
#                                             customer_uid,
#                                             customer_created_at,
#                                             customer_first_name,
#                                             customer_last_name,
#                                             customer_phone_num,
#                                             customer_email,
#                                             customer_address,
#                                             customer_unit,
#                                             customer_city,
#                                             customer_state,
#                                             customer_zip,
#                                             customer_lat,
#                                             customer_long,
#                                             password_salt,
#                                             password_hashed,
#                                             password_algorithm,
#                                             referral_source,
#                                             role,
#                                             user_social_media,
#                                             user_access_token,
#                                             social_timestamp,
#                                             user_refresh_token,
#                                             mobile_access_token,
#                                             mobile_refresh_token,
#                                             social_id
#                                         )
#                                         VALUES
#                                         (
                                        
#                                             \'""" + NewUserID + """\',
#                                             \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
#                                             \'""" + firstName + """\',
#                                             \'""" + lastName + """\',
#                                             \'""" + phone + """\',
#                                             \'""" + email + """\',
#                                             \'""" + address + """\',
#                                             \'""" + unit + """\',
#                                             \'""" + city + """\',
#                                             \'""" + state + """\',
#                                             \'""" + zip_code + """\',
#                                             \'""" + latitude + """\',
#                                             \'""" + longitude + """\',
#                                             \'""" + salt + """\',
#                                             \'""" + password + """\',
#                                             \'""" + algorithm + """\',
#                                             \'""" + referral + """\',
#                                             \'""" + role + """\',
#                                             \'""" + user_social_signup + """\',
#                                             \'""" + user_access_token + """\',
#                                             DATE_ADD(now() , INTERVAL 14 DAY),
#                                             \'""" + user_refresh_token + """\',
#                                             \'""" + mobile_access_token + """\',
#                                             \'""" + mobile_refresh_token + """\',
#                                             \'""" + social_id + """\');"""]
#             #print(customer_insert_query[0])
#             items = execute(customer_insert_query[0], 'post', conn)
#             print(items)
#             if items['code'] != 281:
#                 items['result'] = ""
#                 items['code'] = 480
#                 items['message'] = "Error while inserting values in database"

#                 return items


#             items['result'] = {
#                 'first_name': firstName,
#                 'last_name': lastName,
#                 'customer_uid': NewUserID,
#                 'access_token': user_access_token,
#                 'refresh_token': user_refresh_token,
#                 'access_token': mobile_access_token,
#                 'refresh_token': mobile_refresh_token,
#                 'social_id': social_id


#             }
#             items['message'] = 'Signup successful'
#             items['code'] = 200

#             # Twilio sms service

#             #resp = url_for('sms_service', phone_num='+17327818408', _external=True)
#             #resp = sms_service('+1'+phone, firstName)
#             #print("resp --------", resp)



#             print('sss-----', social_signup)

#             if social_signup == False:
#                 token = s.dumps(email)
#                 msg = Message("Email Verification", sender='ptydtesting@gmail.com', recipients=[email])

#                 print('MESSAGE----', msg)
#                 print('message complete')
#                 link = url_for('confirm', token=token, hashed=password, _external=True)
#                 print('link---', link)
#                 msg.body = "Click on the link {} to verify your email address.".format(link)
#                 print('msg-bd----', msg.body)
#                 mail.send(msg)



#             return items
#         except:
#             print("Error happened while Sign Up")
#             if "NewUserID" in locals():
#                 execute("""DELETE FROM customers WHERE customer_uid = '""" + NewUserID + """';""", 'post', conn)
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)

# # confirmation page
# @app.route('/api/v2/confirm', methods=['GET'])
# def confirm():
#     try:
#         token = request.args['token']
#         hashed = request.args['hashed']
#         print("hased: ", hashed)
#         email = s.loads(token)  # max_age = 86400 = 1 day

#         # marking email confirmed in database, then...
#         conn = connect()
#         query = """UPDATE customers SET email_verified = 1 WHERE customer_email = \'""" + email + """\';"""
#         update = execute(query, 'post', conn)
#         if update.get('code') == 281:
#             # redirect to login page
#             # only for testing on localhost
#             #return redirect('http://localhost:3000/login?email={}&hashed={}'.format(email, hashed))
#             return redirect('https://mealtoyourdoor.netlify.app/?email={}&hashed={}'.format(email, hashed))
#         else:
#             print("Error happened while confirming an email address.")
#             error = "Confirm error."
#             err_code = 401  # Verification code is incorrect
#             return error, err_code
#     except (SignatureExpired, BadTimeSignature) as err:
#         status = 403  # forbidden
#         return str(err), status
#     finally:
#         disconnect(conn)

# def sms_service(phone, name):
#     print(phone)

#     message = client.messages \
#                     .create(
#                          body="Hi " +name+ " thanks for signing up with Serving Fresh",
#                          from_='+18659786905',
#                          to=phone
#                      )
#     print(message.sid)

#     return "Sent"


class createAccount(Resource):
    def post(self):
        response = {}
        items = []
        try:
            conn = connect()
            data = request.get_json(force=True)
            print(data)
            email = data['email']
            firstName = data['first_name']
            lastName = data['last_name']
            phone = data['phone_number']
            address = data['address']
            unit = data['unit'] if data.get('unit') is not None else 'NULL'
            social_id = data['social_id'] if data.get('social_id') is not None else 'NULL'
            city = data['city']
            state = data['state']
            zip_code = data['zip_code']
            latitude = data['latitude']
            longitude = data['longitude']
            referral = data['referral_source']
            role = data['role']
            cust_id = data['cust_id'] if data.get('cust_id') is not None else 'NULL'

            if data.get('social') is None or data.get('social') == "FALSE" or data.get('social') == False or data.get('social') == 'NULL':
                social_signup = False
            else:
                social_signup = True

            print(social_signup)
            get_user_id_query = "CALL new_customer_uid();"
            NewUserIDresponse = execute(get_user_id_query, 'get', conn)

            if NewUserIDresponse['code'] == 490:
                string = " Cannot get new User id. "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = "Internal Server Error."
                return response, 500
            NewUserID = NewUserIDresponse['result'][0]['new_id']

            if social_signup == False:

                salt = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

                password = sha512((data['password'] + salt).encode()).hexdigest()
                print('password------', password)
                algorithm = "SHA512"
                mobile_access_token = 'NULL'
                mobile_refresh_token = 'NULL'
                user_access_token = 'NULL'
                user_refresh_token = 'NULL'
                user_social_signup = 'NULL'
            else:

                mobile_access_token = data['mobile_access_token']
                mobile_refresh_token = data['mobile_refresh_token']
                user_access_token = data['user_access_token']
                user_refresh_token = data['user_refresh_token']
                salt = 'NULL'
                password = 'NULL'
                algorithm = 'NULL'
                user_social_signup = data['social']

                print('ELSE- OUT')

            if cust_id != 'NULL' and cust_id:

                NewUserID = cust_id

                query = '''
                            SELECT user_access_token, user_refresh_token, mobile_access_token, mobile_refresh_token 
                            FROM M4ME.customers
                            WHERE customer_uid = \'''' + cust_id + '''\';
                       '''
                it = execute(query, 'get', conn)
                print('it-------', it)

                if it['result'][0]['user_access_token'] != 'FALSE':
                    user_access_token = it['result'][0]['user_access_token']

                if it['result'][0]['user_refresh_token'] != 'FALSE':
                    user_refresh_token = it['result'][0]['user_refresh_token']

                if it['result'][0]['mobile_access_token'] != 'FALSE':
                    mobile_access_token = it['result'][0]['mobile_access_token']

                if it['result'][0]['mobile_refresh_token'] != 'FALSE':
                    mobile_refresh_token = it['result'][0]['mobile_refresh_token']

                customer_insert_query =  ['''
                                    UPDATE M4ME.customers 
                                    SET 
                                    customer_created_at = \'''' + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + '''\',
                                    customer_first_name = \'''' + firstName + '''\',
                                    customer_last_name = \'''' + lastName + '''\',
                                    customer_phone_num = \'''' + phone + '''\',
                                    customer_address = \'''' + address + '''\',
                                    customer_unit = \'''' + unit + '''\',
                                    customer_city = \'''' + city + '''\',
                                    customer_state = \'''' + state + '''\',
                                    customer_zip = \'''' + zip_code + '''\',
                                    customer_lat = \'''' + latitude + '''\',
                                    customer_long = \'''' + longitude + '''\',
                                    password_salt = \'''' + salt + '''\',
                                    password_hashed = \'''' + password + '''\',
                                    password_algorithm = \'''' + algorithm + '''\',
                                    referral_source = \'''' + referral + '''\',
                                    role = \'''' + role + '''\',
                                    user_social_media = \'''' + user_social_signup + '''\',
                                    social_timestamp  =  DATE_ADD(now() , INTERVAL 14 DAY)
                                    WHERE customer_uid = \'''' + cust_id + '''\';
                                    ''']


            else:

                # check if there is a same customer_id existing
                query = """
                        SELECT customer_email FROM M4ME.customers
                        WHERE customer_email = \'""" + email + "\';"
                print('email---------')
                items = execute(query, 'get', conn)
                if items['result']:

                    items['result'] = ""
                    items['code'] = 409
                    items['message'] = "Email address has already been taken."

                    return items

                if items['code'] == 480:

                    items['result'] = ""
                    items['code'] = 480
                    items['message'] = "Internal Server Error."
                    return items


                # write everything to database
                customer_insert_query = ["""
                                        INSERT INTO M4ME.customers 
                                        (
                                            customer_uid,
                                            customer_created_at,
                                            customer_first_name,
                                            customer_last_name,
                                            customer_phone_num,
                                            customer_email,
                                            customer_address,
                                            customer_unit,
                                            customer_city,
                                            customer_state,
                                            customer_zip,
                                            customer_lat,
                                            customer_long,
                                            password_salt,
                                            password_hashed,
                                            password_algorithm,
                                            referral_source,
                                            role,
                                            user_social_media,
                                            user_access_token,
                                            social_timestamp,
                                            user_refresh_token,
                                            mobile_access_token,
                                            mobile_refresh_token,
                                            social_id
                                        )
                                        VALUES
                                        (
                                        
                                            \'""" + NewUserID + """\',
                                            \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
                                            \'""" + firstName + """\',
                                            \'""" + lastName + """\',
                                            \'""" + phone + """\',
                                            \'""" + email + """\',
                                            \'""" + address + """\',
                                            \'""" + unit + """\',
                                            \'""" + city + """\',
                                            \'""" + state + """\',
                                            \'""" + zip_code + """\',
                                            \'""" + latitude + """\',
                                            \'""" + longitude + """\',
                                            \'""" + salt + """\',
                                            \'""" + password + """\',
                                            \'""" + algorithm + """\',
                                            \'""" + referral + """\',
                                            \'""" + role + """\',
                                            \'""" + user_social_signup + """\',
                                            \'""" + user_access_token + """\',
                                            DATE_ADD(now() , INTERVAL 14 DAY),
                                            \'""" + user_refresh_token + """\',
                                            \'""" + mobile_access_token + """\',
                                            \'""" + mobile_refresh_token + """\',
                                            \'""" + social_id + """\');"""]
            print(customer_insert_query[0])
            items = execute(customer_insert_query[0], 'post', conn)

            if items['code'] != 281:
                items['result'] = ""
                items['code'] = 480
                items['message'] = "Error while inserting values in database"

                return items


            items['result'] = {
                'first_name': firstName,
                'last_name': lastName,
                'customer_uid': NewUserID,
                'access_token': user_access_token,
                'refresh_token': user_refresh_token,
                'access_token': mobile_access_token,
                'refresh_token': mobile_refresh_token,
                'social_id': social_id


            }
            items['message'] = 'Signup successful'
            items['code'] = 200

            print('sss-----', social_signup)
            return items

        except:
            print("Error happened while Sign Up")
            if "NewUserID" in locals():
                execute("""DELETE FROM customers WHERE customer_uid = '""" + NewUserID + """';""", 'post', conn)
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class email_verification(Resource):
    def post(self):

        try:
            conn = connect()

            data = request.get_json(force=True)
            print(data)
            email = data['email']
            query = """
                    SELECT password_hashed
                    FROM M4ME.customers c
                    WHERE customer_email = \'""" + email + """\'
                    """
            items = execute(query, 'get', conn)
            print(items)
            if not items['result']:

                items['message'] = "Customer email doesn't exists"
                items['code'] = 404
                return items
            if items['result'][0]['password_hashed'] == '':
                items['message'] = "Customer password doesn't exists"
                items['code'] = 405
                return items

            token = s.dumps(email)
            print(token)
            password = items['result'][0]['password_hashed']
            print(password)
            # msg = Message("Test email", sender='support@mealsfor.me', recipients=["pmarathay@gmail.com"]) 
            # msg.body = "Hi !\n\n"\
            # "We are excited to send you your Summary report for delivery date. Please find the report in the attachment. \n"\
            # "Email support@servingfresh.me if you run into any problems or have any questions.\n" \
            # "Thx - The Serving Fresh Team\n\n" 
            # print('msg-bd----', msg.body) 
            # print('msg-') 
            # mail.send(msg)
            msg = Message("Email Verification", sender='support@mealsfor.me', recipients=[email])

            print('MESSAGE----', msg)
            print('message complete')
            print("1")
            link = url_for('confirm', token=token, hashed=password, _external=True)
            print("2")
            print('link---', link)
            msg.body = "Click on the link {} to verify your email address.".format(link)
            print('msg-bd----', msg.body)
            mail.send(msg)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




# confirmation page
@app.route('/api/v2/confirm', methods=['GET'])
def confirm():
    try:
        token = request.args['token']
        hashed = request.args['hashed']
        print("hased: ", hashed)
        email = s.loads(token)  # max_age = 86400 = 1 day

        # marking email confirmed in database, then...
        conn = connect()
        query = """UPDATE customers SET email_verified = 1 WHERE customer_email = \'""" + email + """\';"""
        update = execute(query, 'post', conn)
        if update.get('code') == 281:
            # redirect to login page
            # only for testing on localhost
            #return redirect('http://localhost:3000/login?email={}&hashed={}'.format(email, hashed))
            return redirect('https://mealsfor.me/login?email={}&hashed={}'.format(email, hashed)) #need to change url
            #https://mealtoyourdoor.netlify.app/choose-plan
            #return redirect('https://mealtoyourdoor.netlify.app/home')
        else:
            print("Error happened while confirming an email address.")
            error = "Confirm error."
            err_code = 401  # Verification code is incorrect
            return error, err_code
    except (SignatureExpired, BadTimeSignature) as err:
        status = 403  # forbidden
        return str(err), status
    finally:
        disconnect(conn)

def sms_service(phone, name):
    print(phone)

    message = client.messages \
                    .create(
                         body="Hi " +name+ " thanks for signing up with Serving Fresh",
                         from_='+18659786905',
                         to=phone
                     )
    print(message.sid)

    return "Sent"




class Login(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            email = data['email']
            password = data.get('password')
            social_id = data.get('social_id')
            signup_platform = data.get('signup_platform')
            query = """
                    # CUSTOMER QUERY 1: LOGIN
                    SELECT customer_uid,
                        customer_last_name,
                        customer_first_name,
                        customer_email,
                        password_hashed,
                        email_verified,
                        user_social_media,
                        user_access_token,
                        user_refresh_token,
                        user_access_token,
                        user_refresh_token,
                        social_id
                    FROM M4ME.customers c
                    -- WHERE customer_email = "1m4kfun@gmail.com";
                    WHERE customer_email = \'""" + email + """\';
                    """
            items = execute(query, 'get', conn)
            print('Password', password)
            print(items)

            if items['code'] != 280:
                response['message'] = "Internal Server Error."
                response['code'] = 500
                return response
            elif not items['result']:
                items['message'] = 'Email Not Found. Please signup'
                items['result'] = ''
                items['code'] = 404
                return items
            else:
                print(items['result'])
                print('sc: ', items['result'][0]['user_social_media'])


                # checks if login was by social media
                if password and items['result'][0]['user_social_media'] != 'NULL' and items['result'][0]['user_social_media'] != None:
                    response['message'] = "Need to login by Social Media"
                    response['code'] = 401
                    return response

               # nothing to check
                elif (password is None and social_id is None) or (password is None and items['result'][0]['user_social_media'] == 'NULL'):
                    response['message'] = "Enter password else login from social media"
                    response['code'] = 405
                    return response

                # compare passwords if user_social_media is false
                elif (items['result'][0]['user_social_media'] == 'NULL' or items['result'][0]['user_social_media'] == None) and password is not None:

                    if items['result'][0]['password_hashed'] != password:
                        items['message'] = "Wrong password"
                        items['result'] = ''
                        items['code'] = 406
                        return items

                    if ((items['result'][0]['email_verified']) == '0') or (items['result'][0]['email_verified'] == "FALSE"):
                        response['message'] = "Account need to be verified by email."
                        response['code'] = 407
                        return response

                # compare the social_id because it never expire.
                elif (items['result'][0]['user_social_media']) != 'NULL':

                    if signup_platform != items['result'][0]['user_social_media']:
                        items['message'] = "Wrong social media used for signup. Use \'" + items['result'][0]['user_social_media'] + "\'."
                        items['result'] = ''
                        items['code'] = 411
                        return items

                    if (items['result'][0]['social_id'] != social_id):
                        print(items['result'][0]['social_id'])

                        items['message'] = "Cannot Authenticated. Social_id is invalid"
                        items['result'] = ''
                        items['code'] = 408
                        return items

                else:
                    string = " Cannot compare the password or social_id while log in. "
                    print("*" * (len(string) + 10))
                    print(string.center(len(string) + 10, "*"))
                    print("*" * (len(string) + 10))
                    response['message'] = string
                    response['code'] = 500
                    return response
                del items['result'][0]['password_hashed']
                del items['result'][0]['email_verified']

                query = "SELECT * from M4ME.customers WHERE customer_email = \'" + email + "\';"
                items = execute(query, 'get', conn)
                items['message'] = "Authenticated successfully."
                items['code'] = 200
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



# class Login(Resource):
#     def post(self):
#         response = {}
#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             email = data['email']
#             password = data.get('password')
#             refresh_token = data.get('token')
#             signup_platform = data.get('signup_platform')
#             query = """
#                     # CUSTOMER QUERY 1: LOGIN
#                     SELECT customer_uid,
#                         customer_last_name,
#                         customer_first_name,
#                         customer_email,
#                         password_hashed,
#                         email_verified,
#                         user_social_media,
#                         user_access_token,
#                         user_refresh_token
#                     FROM M4ME.customers c
#                     -- WHERE customer_email = "1m4kfun@gmail.com";
#                     WHERE customer_email = \'""" + email + """\';
#                     """
#             items = execute(query, 'get', conn)
#             print('Password', password)
#             print(items)

#             if items['code'] != 280:
#                 response['message'] = "Internal Server Error."
#                 response['code'] = 500
#                 return response
#             elif not items['result']:
#                 items['message'] = 'Email Not Found. Please signup'
#                 items['result'] = ''
#                 items['code'] = 404
#                 return items
#             else:
#                 print(items['result'])
#                 print('sc: ', items['result'][0]['user_social_media'])


#                 # checks if login was by social media
#                 if password and items['result'][0]['user_social_media'] != 'NULL' and items['result'][0]['user_social_media'] != None:
#                     response['message'] = "Need to login by Social Media"
#                     response['code'] = 401
#                     return response

#                # nothing to check
#                 elif (password is None and refresh_token is None) or (password is None and items['result'][0]['user_social_media'] == 'NULL'):
#                     response['message'] = "Enter password else login from social media"
#                     response['code'] = 405
#                     return response

#                 # compare passwords if user_social_media is false
#                 elif (items['result'][0]['user_social_media'] == 'NULL' or items['result'][0]['user_social_media'] == None) and password is not None:

#                     if items['result'][0]['password_hashed'] != password:
#                         items['message'] = "Wrong password"
#                         items['result'] = ''
#                         items['code'] = 406
#                         return items

#                     if ((items['result'][0]['email_verified']) == '0') or (items['result'][0]['email_verified'] == "FALSE"):
#                         response['message'] = "Account need to be verified by email."
#                         response['code'] = 407
#                         return response

#                 # compare the refresh token because it never expire.
#                 elif (items['result'][0]['user_social_media']) != 'NULL':
#                     '''
#                     keep
#                     if signup_platform != items['result'][0]['user_social_media']:
#                         items['message'] = "Wrong social media used for signup. Use \'" + items['result'][0]['user_social_media'] + "\'."
#                         items['result'] = ''
#                         items['code'] = 401
#                         return items
#                     '''
#                     if (items['result'][0]['user_refresh_token'] != refresh_token):
#                         print(items['result'][0]['user_refresh_token'])

#                         items['message'] = "Cannot Authenticated. Token is invalid"
#                         items['result'] = ''
#                         items['code'] = 408
#                         return items

#                 else:
#                     string = " Cannot compare the password or refresh token while log in. "
#                     print("*" * (len(string) + 10))
#                     print(string.center(len(string) + 10, "*"))
#                     print("*" * (len(string) + 10))
#                     response['message'] = string
#                     response['code'] = 500
#                     return response
#                 del items['result'][0]['password_hashed']
#                 del items['result'][0]['email_verified']

#                 query = "SELECT * from M4ME.customers WHERE customer_email = \'" + email + "\';"
#                 items = execute(query, 'get', conn)
#                 items['message'] = "Authenticated successfully."
#                 items['code'] = 200
#                 return items

#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)






class AppleLogin (Resource):

    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            token = request.form.get('id_token')
            access_token = request.form.get('code')
            print(token)
            if token:
                print('INN')
                data = jwt.decode(token, verify=False)
                print('data-----', data)
                email = data.get('email')

                print(data, email)
                if email is not None:
                    sub = data['sub']
                    query = """
                    SELECT customer_uid,
                        customer_last_name,
                        customer_first_name,
                        customer_email,
                        password_hashed,
                        email_verified,
                        user_social_media,
                        user_access_token,
                        user_refresh_token,
                        social_id
                    FROM M4ME.customers c
                    WHERE social_id = \'""" + sub + """\';
                    """
                    items = execute(query, 'get', conn)
                    print(items)

                    if items['code'] != 280:
                        items['message'] = "Internal error"
                        return items


                    # new customer


                    if not items['result']:
                        print('New customer')
                        items['message'] = "Social_id doesn't exists Please go to the signup page"
                        get_user_id_query = "CALL new_customer_uid();"
                        NewUserIDresponse = execute(get_user_id_query, 'get', conn)

                        if NewUserIDresponse['code'] == 490:
                            string = " Cannot get new User id. "
                            print("*" * (len(string) + 10))
                            print(string.center(len(string) + 10, "*"))
                            print("*" * (len(string) + 10))
                            response['message'] = "Internal Server Error."
                            response['code'] = 500
                            return response

                        NewUserID = NewUserIDresponse['result'][0]['new_id']
                        user_social_signup = 'APPLE'
                        print('NewUserID', NewUserID)


                        customer_insert_query = """
                                    INSERT INTO M4ME.customers 
                                    (
                                        customer_uid,
                                        customer_created_at,
                                        customer_email,
                                        user_social_media,
                                        user_refresh_token,
                                        user_access_token,
                                        social_id,
                                        social_timestamp
                                    )
                                    VALUES
                                    (
                                    
                                        \'""" + NewUserID + """\',
                                        \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
                                        \'""" + email + """\',
                                        \'""" + user_social_signup + """\',
                                        \'""" + access_token + """\',
                                        \'""" + access_token + """\',
                                        \'""" + sub + """\',
                                        DATE_ADD(now() , INTERVAL 1 DAY)
                                    );"""

                        item = execute(customer_insert_query, 'post', conn)

                        print('INSERT')

                        if item['code'] != 281:
                            item['message'] = 'Check insert sql query'
                            return item
                        print('successful redirect to signup')
                        return redirect("https://mealsfor.me/social-sign-up?id=" + NewUserID)


                    # Existing customer

                    print('existing-------')
                    print(items['result'][0]['user_social_media'])
                    print(items['result'][0]['social_id'])

                    if items['result'][0]['user_social_media'] != "APPLE":
                        print('1-----')
                        items['message'] = "Wrong social media used for signup. Use \'" + items['result'][0]['user_social_media'] + "\'."
                        items['code'] = 400
                        return redirect("https://mealsfor.me/")

                    elif items['result'][0]['social_id'] != sub:
                        print('20-----')
                        items['message'] = "social_id mismatch"
                        items['code'] = 400
                        return redirect("https://mealsfor.me/")

                    else:
                        print('successful redirect to farms')
                        return redirect("https://mealsfor.me/choose-plan?customer_uid=" + items['result'][0]['customer_uid'])



                else:
                    items['message'] = "Social_id not returned by Apple LOGIN"
                    items['code'] = 400
                    return items


            else:
                response = {
                    "message": "Token not found in Apple's Response",
                    "code": 400
                }
                return response
        except:
            raise BadRequest("Request failed, please try again later.")




# class AppleLogin (Resource):

#     def post(self):
#         response = {}
#         items = {}
#         try:
#             conn = connect()
#             token = request.form.get('id_token')
#             print(token)
#             if token:
#                 print('INN')
#                 data = jwt.decode(token, verify=False)
#                 print('data-----', data)
#                 email = data.get('email')

#                 print(data, email)
#                 if email is not None:
#                     sub = data['sub']
#                     query = """
#                     SELECT customer_uid,
#                         customer_last_name,
#                         customer_first_name,
#                         customer_email,
#                         password_hashed,
#                         email_verified,
#                         user_social_media,
#                         user_access_token,
#                         user_refresh_token
#                     FROM M4ME.customers c
#                     WHERE customer_email = \'""" + email + """\';
#                     """
#                     items = execute(query, 'get', conn)
#                     print(items)

#                     if items['code'] != 280:
#                         items['message'] = "Internal error"
#                         return items


#                     # new customer
#                     if not items['result']:
#                         items['message'] = "Email doesn't exists Please go to the signup page"
#                         get_user_id_query = "CALL new_customer_uid();"
#                         NewUserIDresponse = execute(get_user_id_query, 'get', conn)

#                         if NewUserIDresponse['code'] == 490:
#                             string = " Cannot get new User id. "
#                             print("*" * (len(string) + 10))
#                             print(string.center(len(string) + 10, "*"))
#                             print("*" * (len(string) + 10))
#                             response['message'] = "Internal Server Error."
#                             response['code'] = 500
#                             return response

#                         NewUserID = NewUserIDresponse['result'][0]['new_id']
#                         user_social_signup = 'APPLE'
#                         print('NewUserID', NewUserID)
#                         #only works for mysql, and only allows for inserting one row at a time
#                         customer_insert_query = """
#                                     INSERT INTO M4ME.customers 
#                                     set
#                                         customer_uid = \'""" + NewUserID + """\',
#                                         customer_created_at = \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
#                                         customer_email = \'""" + email + """\',
#                                         user_social_media = \'""" + user_social_signup + """\',
#                                         user_refresh_token = \'""" + sub + """\'
#                                     ;"""


#                                     #original code for reference
#                                     #   INSERT INTO M4ME.customers 
#                                     # (
#                                     #     customer_uid,
#                                     #     customer_created_at,
#                                     #     customer_email,
#                                     #     user_social_media,
#                                     #     user_refresh_token
#                                     # )
#                                     # VALUES
#                                     # (
                                    
#                                     #     \'""" + NewUserID + """\',
#                                     #     \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
#                                     #     \'""" + email + """\',
#                                     #     \'""" + user_social_signup + """\',
#                                     #     \'""" + sub + """\'
#                                     # );"""


#                         item = execute(customer_insert_query, 'post', conn)

#                         print('INSERT')

#                         #if sql works, and new user then social sign up
#                         if item['code'] != 281:
#                             item['message'] = 'Check insert sql query'
#                             return item
#                         #applelogin changes
#                         return redirect("https://mealtoyourdoor.netlify.app/social-sign-up?id=" + NewUserID)
#                         #return redirect("http://localhost:3000/social-sign-up?id=" + NewUserID)

#                     # Existing customer

#                     #if we get back a refresh token
#                     if items['result'][0]['user_refresh_token']:
#                         print(items['result'][0]['user_social_media'], items['result'][0]['user_refresh_token'])

#                         #if result is not apple
#                         if items['result'][0]['user_social_media'] != "APPLE":
#                             items['message'] = "Wrong social media used for signup. Use \'" + items['result'][0]['user_social_media'] + "\'."
#                             items['code'] = 400
#                             return redirect("https://mealtoyourdoor.netlify.app/")
#                             #return redirect("http://localhost:3000")
#                             #return items

#                         #if referesh token does not match
#                         elif items['result'][0]['user_refresh_token'] != sub:
#                             items['message'] = "Token mismatch"
#                             items['code'] = 400
#                             return redirect("https://mealtoyourdoor.netlify.app/")
#                             #return redirect("http://localhost:3000")
#                             #return items

#                         #if social media = apple, and token matches, send to meals selected
#                         else:
#                             #applelogin changes
#                             # return redirect("http://localhost:3000/farms?id=" + items['result'][0]['customer_uid'])
#                             return redirect("https://mealtoyourdoor.netlify.app/choose-plan?customer_uid=" + items['result'][0]['customer_uid'])
#                             #return redirect("http://localhost:3000/select-meal?id=" + items['result'][0]['customer_uid'])

#                 else:
#                     items['message'] = "Email not returned by Apple LOGIN"
#                     items['code'] = 400
#                     return items


#             else:
#                 response = {
#                     "message": "Token not found in Apple's Response",
#                     "code": 400
#                 }
#                 return response
#         except:
#             raise BadRequest("Request failed, please try again later.")





class Change_Password(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            customer_uid = data['customer_uid']
            old_pass = data['old_password']
            new_pass = data['new_password']
            query = """
                        SELECT customer_email, password_hashed, password_salt, password_algorithm
                        FROM customers WHERE customer_uid = '""" + customer_uid + """';
                    """
            query_res = simple_get_execute(query, "CHANGE PASSWORD QUERY", conn)
            if query_res[1] != 200:
                return query_res
            # because the front end will send back plain password, We need to salt first
            # checking for identity
            old_salt = query_res[0]['result'][0]['password_salt']
            old_password_hashed = sha512((old_pass + old_salt).encode()).hexdigest()
            if old_password_hashed != query_res[0]['result'][0]['password_hashed']:
                response['message'] = "Wrong Password"
                return response, 401
            # create a new salt and hashing the new password
            new_salt = getNow()
            algorithm = query_res[0]['result'][0]['password_algorithm']
            if algorithm == "SHA512" or algorithm is None or algorithm == "":
                new_password_hashed = sha512((new_pass + new_salt).encode()).hexdigest()
            else: # if we have saved the hashing algorithm in our database,
                response['message'] = "Cannot change Password. Need the algorithm to hashed the new password."
                return response, 500
            update_query = """
                            UPDATE customers SET password_salt = '""" + new_salt + """', 
                                password_hashed = '""" + new_password_hashed + """'
                                WHERE customer_uid = '""" + customer_uid + """';
                            """
            update_query_res = simple_post_execute([update_query], ["UPDATE PASSWORD"], conn )
            if update_query_res[1] != 201:
                return update_query_res
            response['message'] = "Password updated."
            return response, 201
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Reset_Password(Resource):
    def get_random_string(self, stringLength=8):
        lettersAndDigits = string.ascii_letters + string.digits
        return "".join([random.choice(lettersAndDigits) for i in range(stringLength)])

    def get(self):
        response = {}
        try:
            conn = connect()
            # search for email;
            email = request.args['email']

            query = """SELECT * FROM customers
                    WHERE customer_email ='""" + email + "';"
            customer_lookup = simple_get_execute(query, "RESET PASSWORD QUERY", conn)
            if customer_lookup[1] != 200:
                return customer_lookup
            customer_uid = customer_lookup[0]['result'][0]['customer_uid']
            pass_temp = self.get_random_string()
            salt = getNow()
            pass_temp_hashed = sha512((pass_temp + salt).encode()).hexdigest()
            query = """
                    UPDATE customers SET password_hashed = '""" + pass_temp_hashed + """'
                     , password_salt = '""" + salt + """' 
                     WHERE customer_uid = '""" + customer_uid + """';
                    """
            # update database with temp password
            query_result = simple_post_execute([query], ["UPDATE RESET PASSWORD"], conn)
            if query_result[1]!= 201:
                return query_result
            # send an email to client
            print("mail 1") 
            msg = Message("Email Verification", sender='support@mealsfor.me', recipients=[email], bcc='support@mealsfor.me')
            msg.body = "Your temporary password is {}. Please use it to reset your password".format(pass_temp)
            print("mail 2")
            # msg2 = Message("Email Verification", sender='support@mealsfor.me', recipients='support@mealsfor.me')
            # supportmessage = str(email) + " has requested a temporary password, and it is {}."
            # #print(supportmessage)
            # msg2.body = supportmessage.format(pass_temp)
            print("ready to send")
            mail.send(msg)
            # print("sending 2")
            # print(msg2.body)
            # print("actual sending 2")
            # mail.send(msg2)
            print("both sent")
            response['message'] = "A temporary password has been sent"
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selected(Resource):
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            query = """
                    # CUSTOMER QUERY 3: ALL MEAL SELECTIONS BY CUSTOMER  (INCLUDES HISTORY)
                    SELECT * FROM M4ME.latest_combined_meal lcm
                    LEFT JOIN M4ME.lplp
                        ON lcm.sel_purchase_id = lplp.purchase_id
                    WHERE pur_customer_uid = '""" + customer_uid + """'; 
                    """

            
            items = execute(query, 'get', conn)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Meals selected"
                items['code'] = 200
                #return items
            return items


            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selected_Specific(Resource):
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            purchase_id = request.args['purchase_id']
            menu_date = request.args['menu_date']
            query = """
                    # CUSTOMER QUERY 3: ALL MEAL SELECTIONS BY CUSTOMER  (INCLUDES HISTORY)
                    SELECT * FROM M4ME.latest_combined_meal lcm
                    LEFT JOIN M4ME.lplp
                        ON lcm.sel_purchase_id = lplp.purchase_id
                    WHERE pur_customer_uid = '""" + customer_uid + """'
                    and purchase_id = '""" + purchase_id + """'
                    and sel_menu_date= '""" + menu_date + """';
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Meals selected"
                items['code'] = 200
                #return items
            return items


            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class Get_Upcoming_Menu(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    # CUSTOMER QUERY 4: UPCOMING MENUS
                    SELECT * FROM M4ME.menu
                    LEFT JOIN M4ME.meals m
                        ON menu.menu_meal_id = m.meal_uid
                    WHERE menu_date > CURDATE()
                    order by menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Menu selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Get_Latest_Purchases_Payments(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            query = """
                    # CUSTOMER QUERY 2: CUSTOMER LATEST PURCHASE AND LATEST PAYMENT HISTORY
                    # NEED CUSTOMER ADDRESS IN CASE CUSTOMER HAS NOT ORDERED BEFORE
                    SELECT * FROM M4ME.lplp lp
                    LEFT JOIN M4ME.customers c
                        ON lp.pur_customer_uid = c.customer_uid
                    WHERE pur_customer_uid = '""" + customer_uid + """'
                    and purchase_status = "ACTIVE"
                    and items like "%200-000002%";
                    """
            response = simple_get_execute(query, __class__.__name__, conn)
            if response[1] != 200:
                return response[1]
            except_list = ['password_hashed', 'password_salt', 'password_algorithm']
            for i in range(len(response[0]['result'])):
                for key in except_list:
                     if response[0]['result'][i].get(key) is not None:
                        del response[0]['result'][i][key]
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Next_Billing_Date(Resource):
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            query = """
                        # CUSTOMER QUERY 5: NEXT SUBSCRIPTION BILLING DATE (WITH TRUE_SKIPS)
                        SELECT *,
                            IF (nbd.true_skips > 0,
                            ADDDATE(nbd.start_delivery_date, (nbd.num_issues + nbd.true_skips) * 7 / nbd.deliveries_per_week - 3),
                            ADDDATE(nbd.start_delivery_date, (nbd.num_issues +        0      ) * 7 / nbd.deliveries_per_week - 3) ) AS next_billing_date
                        FROM (
                            SELECT lplpibr.*,
                                si.*,
                                ts.skip_count
                            FROM M4ME.lplp_items_by_row AS lplpibr
                            LEFT JOIN M4ME.subscription_items si
                                ON lplpibr.lplpibr_jt_item_uid = si.item_uid
                            LEFT JOIN 
                                (SELECT COUNT(delivery_day) AS skip_count FROM
                                    (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM meals_selected
                                        WHERE sel_purchase_id = '""" + info_res['purchase_id'] + """'
                                        GROUP BY sel_menu_date) AS GB
                                        INNER JOIN meals_selected S
                                        ON S.sel_purchase_id = GB.sel_purchase_id
                                            AND S.sel_menu_date = GB.sel_menu_date
                                            AND S.selection_time = GB.max_selection_time
                                WHERE S.sel_menu_date >= '""" + start_delivery_date.strftime("%Y-%m-%d %H-%M-%S") + """'
                                    AND S.sel_menu_date <= '""" + datetime.now().strftime("%Y-%m-%d %H-%M-%S") + """'
                                    AND delivery_day = 'SKIP'
                                ORDER BY S.sel_menu_date) as ts
                        WHERE lplpibr_customer_uid = '""" + customer_uid + """';
                        """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Next_Addon_Charge(Resource):
    def get(self):
        try:
            conn = connect()
            purchase_uid = request.args['purchase_uid']
            query = """
                        # CUSTOMER QUERY 6: NEXT ADDONS BILLING DATE AND AMOUNT
                        SELECT *,
                            MIN(sel_menu_date)
                        FROM (
                                SELECT *,
                                        SUM(addon_charge)
                                FROM (
                                    SELECT *,
                                        jt_qty * jt_price AS addon_charge
                                    FROM M4ME.selected_addons_by_row
                                    WHERE sel_menu_date >= ADDDATE(CURDATE(), -28) ) 
                                    AS meal_aoc
                                GROUP BY selection_uid
                                ORDER BY sel_purchase_id, sel_menu_date ASC) 
                            AS sum_aoc
                        WHERE sel_purchase_id = '""" + purchase_uid + """'
                        GROUP BY sel_purchase_id;
                        """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)






class AccountSalt(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()

            data = request.get_json(force=True)
            print(data)
            email = data['email']
            query = """
                    SELECT password_algorithm, 
                            password_salt,
                            user_social_media 
                    FROM M4ME.customers cus
                    WHERE customer_email = \'""" + email + """\';
                    """
            items = execute(query, 'get', conn)
            if not items['result']:
                items['message'] = "Email doesn't exists"
                items['code'] = 404
                return items
            if items['result'][0]['user_social_media'] != 'NULL':
                items['message'] = """Social Signup exists. Use \'""" + items['result'][0]['user_social_media'] + """\' """
                items['code'] = 401
                return items
            items['message'] = 'SALT sent successfully'
            items['code'] = 200
            return items
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)   





# class AccountSalt(Resource):
#     def post(self):
#         items = {}
#         try:
#             conn = connect()
#             data = request.get_json(force=True)

#             email = data['email']
#             print("1")
#             query = """
#                         SELECT user_social_media
#                         FROM customers cus
#                         WHERE customer_email = \'""" + email + """\';
#                         """
#             items = simple_get_execute(query, __class__.__name__, conn)
#             #print("2")
#             #print(items[0]['result'][0]["user_social_media"])
#             #customer_res['result'][0]['password_hashed']
#             #print("3")
#             if items[0]['result'][0]["user_social_media"]is not None:
#                 #print("4")
#                 return items[0]['result'][0]["user_social_media"]
#             else:
#                 query = """
#                         SELECT password_algorithm, 
#                                 password_salt 
#                         FROM customers cus
#                         WHERE customer_email = \'""" + email + """\';
#                         """
#                 return simple_get_execute(query, __class__.__name__, conn)
#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)





#used pur_business_uid
class Checkout(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            customer_uid = data['customer_uid']
            business_uid = data['business_uid'] if data.get('business_uid') is not None else 'NULL'
            delivery_first_name = data['delivery_first_name']
            delivery_last_name = data['delivery_last_name']
            delivery_email = data['delivery_email']
            delivery_phone = data['delivery_phone']
            delivery_address = data['delivery_address']
            #delivery_unit = data['delivery_unit']
            delivery_unit = data['unit'] if data.get('unit') is not None else 'NULL'
            delivery_city = data['delivery_city']
            delivery_state = data['delivery_state']
            delivery_zip = data['delivery_zip']
            delivery_instructions = "'" + data['delivery_instructions'] + "'" if data.get('delivery_instructions') else 'NULL'
            delivery_longitude = data['delivery_longitude']
            delivery_latitude = data['delivery_latitude']

            items = "'[" + ", ".join([str(item).replace("'", "\"") if item else "NULL" for item in data['items']]) + "]'"
            order_instructions = "'" + data['order_instructions'] + "'" if data.get('order_instructions') is not None else 'NULL'
            purchase_notes = "'" + data['purchase_notes'] + "'" if data.get('purchase_notes') is not None else 'NULL'
            amount_due = data['amount_due']
            amount_discount = data['amount_discount']
            amount_paid = data['amount_paid']
            print("test 0.7")
            cc_num = data['cc_num']
            cc_exp_date = data['cc_exp_year'] + data['cc_exp_month'] + "01"
            cc_cvv = data['cc_cvv']
            cc_zip = data['cc_zip']
            charge_id = data['charge_id']
            payment_type = data['payment_type']

            taxes = data['tax']
            tip = data['tip']
            service_fee = data['service_fee']
            delivery_fee = data['delivery_fee']
            subtotal = data['subtotal']

            print(data['charge_id'])
            print(data['payment_type'])

            amount_must_paid = float(amount_due) - float(amount_paid) - float(amount_discount)
            print("0")
            # We should sanitize the variable before writting into database.
            # must pass these check first
            if items == "'[]'":
                raise BadRequest()
            
            purchaseId = get_new_purchaseID(conn)
            if purchaseId[1] == 500:
                print(purchaseId[0])
                response['message'] = "Internal Server Error."
                return response, 500
            paymentId = get_new_paymentID(conn)
            if paymentId[1] == 500:
                print(paymentId[0])
                response['message'] = "Internal Server Error."
                return response, 500
            # User authenticated
            # check the customer_uid and see what kind of registration.
            # if it was registered by email then check the password.
            customer_query = """SELECT * FROM customers WHERE customer_uid = '""" + data['customer_uid'] + """';"""
            customer_res = execute(customer_query, 'get', conn)

            if customer_res['code'] != 280 or not customer_res['result']:
                response['message'] = "Could not authenticate user"
                return response, 401
            # if customer_res['result'][0]['password_hashed'] is not None: original
            #print(customer_res['result'][0]['password_hashed'])
            #print(data['salt'])
            print("1")
            # if customer_res['result'][0]['password_hashed'] != 'NULL' and customer_res['result'][0]['password_hashed'] is not None:
            #     print("1.3")
            #     print(customer_res['result'][0]['password_hashed'])
            #     print(data['salt'])
            #     if customer_res['result'][0]['password_hashed'] != data['salt']:
            #         print("1.35")
            #         response['message'] = "Could not authenticate user. Wrong Password"
            #         return response, 401
            # Validate credit card
            # if str(data['cc_num'][0:12]) == "XXXXXXXXXXXX":
            #     latest_purchase = get_latest_purchases(business_id, customer_uid)
            #     if latest_purchase['result'] is None:
            #         response['message'] = "Credit card number is invalid."
            #         return response, 400
            #     if str(latest_purchase['result']['cc_num'][:-4refund_calculator]) != str(data['cc_num'][:-4]):
            #         response['message'] = "Credit card number is invalid."
            #         return response, 400
            #     cc_num = latest_purchase['result']['cc_num']

            # create a stripe charge and make sure that charge is successful before writing it into database
            # we should use Idempotent key to prevent sending multiple payment requests due to connection fail.
            # Also, It is not safe for using Strip Charge API. We should use Stripe Payment Intent API and its SDKs instead.
            print("1.4")
            try:
                print("1.5")
                # create a token for stripe
                #card_dict = {"number": data['cc_num'], "exp_month": int(data['cc_exp_month']), "exp_year": int(data['cc_exp_year']),"cvc": data['cc_cvv']}
                #print(card_dict)
                #stripe_charge = {}
                
                # print(stripe.Token.create(card=card_dict))
                # print("1.6")
                # try:
                #     card_token = stripe.Token.create(card=card_dict)
                #     print("2")
                #     if int(amount_must_paid) > 0:
                #         stripe_charge = stripe.Charge.create(
                #             amount=int(round(amount_must_paid*100, 0)),
                #             currency="usd",
                #             source=card_token,
                #             description="Charge customer for new Subscription")
                #     # update amount_paid. At this point, the payment has been processed so amount_paid == amount_due
                #     amount_paid = amount_due
                # except stripe.error.CardError as e:
                #     # Since it's a decline, stripe.error.CardError will be caught
                #     response['message'] = e.error.message
                #     return response, 400

                # update coupon table
                coupon_id = data.get('coupon_id')
                if str(coupon_id) != "" and coupon_id is not None:
                    # update coupon table
                    coupon_id = "'" + coupon_id + "'"
                    coupon_query = """UPDATE coupons SET num_used = num_used + 1
                                WHERE coupon_id =  """ + str(coupon_id) + ";"
                    res = execute(coupon_query, 'post', conn)
                else:
                    coupon_id = 'NULL'

                #charge_id = 'NULL' if stripe_charge.get('id') is None else "'" + stripe_charge.get('id') + "'"
                # charge_id = 'TEST'

                #calculate the start_delivery_date

                dayOfWeek = datetime.now().weekday()

                # Get the soonest Thursday, same day if today is Thursday
                thurs = datetime.now() + timedelta(days=(3 - dayOfWeek) % 7)
                print("problem start")
                # If today is Thursday after 4PM'
                if thurs.date() == datetime.now().date() and datetime.now().hour >= 16:
                    thurs += timedelta(days=7)

                #the next saturday
                start_delivery_date = (thurs + timedelta(days=2)).strftime("%Y-%m-%d 00:00:00")

                #find tax, delivery fee etc
                find_zone = '''
                            select * from zones
                            where 
                            '''
                # write into Payments table

                
                queries = [
                            '''
                            INSERT INTO M4ME.payments
                            SET payment_uid = \'''' + paymentId + '''\',
                                payment_time_stamp = \'''' + getNow() + '''\',
                                start_delivery_date = \'''' + start_delivery_date + '''\',
                                payment_id = \'''' + paymentId + '''\',
                                pay_purchase_id = \'''' + purchaseId + '''\',
                                pay_purchase_uid = \'''' + purchaseId + '''\',
                                amount_due = \'''' + amount_due + '''\',
                                amount_discount = \'''' + amount_discount + '''\',
                                amount_paid = \'''' + amount_paid + '''\',
                                pay_coupon_id = ''' + coupon_id + ''',
                                charge_id = \'''' + charge_id + '''\',
                                payment_type = \'''' + payment_type + '''\',
                                info_is_Addon = 'FALSE',
                                cc_num = \'''' + cc_num  + '''\', 
                                cc_exp_date = \'''' + cc_exp_date + '''\', 
                                cc_cvv = \'''' + cc_cvv + '''\', 
                                cc_zip = \'''' + cc_zip + '''\',
                                taxes = \'''' + taxes + '''\',
                                driver_tip = \'''' + tip + '''\',
                                service_fee = \'''' + service_fee + '''\',
                                delivery_fee = \'''' + service_fee + '''\',
                                subtotal = \'''' + subtotal + '''\';
                            ''',
                            '''
                            INSERT INTO  M4ME.purchases
                            SET purchase_uid = \'''' + purchaseId + '''\',
                                purchase_date = \'''' + getNow() + '''\',
                                purchase_id = \'''' + purchaseId + '''\',
                                purchase_status = 'ACTIVE',
                                pur_customer_uid = \'''' + customer_uid + '''\',
                                delivery_first_name = \'''' + delivery_first_name + '''\',
                                delivery_last_name = \'''' + delivery_last_name + '''\',
                                delivery_email = \'''' + delivery_email + '''\',
                                delivery_phone_num = \'''' + delivery_phone + '''\',
                                delivery_address = \'''' + delivery_address + '''\',
                                delivery_unit = \'''' + delivery_unit + '''\',
                                delivery_city = \'''' + delivery_city + '''\',
                                delivery_state = \'''' + delivery_state + '''\',
                                delivery_zip = \'''' + delivery_zip + '''\',
                                delivery_instructions = ''' + delivery_instructions + ''',
                                delivery_longitude = \'''' + delivery_longitude + '''\',
                                delivery_latitude = \'''' + delivery_latitude + '''\',
                                items = ''' + items + ''',
                                order_instructions = ''' + order_instructions + ''',
                                purchase_notes = ''' + purchase_notes + ''';
                            '''
                            ]
                response = simple_post_execute(queries, ["PAYMENTS", "PURCHASES"], conn)
                if response[1] == 201:
                    response[0]['payment_id'] = paymentId
                    response[0]['purchase_id'] = purchaseId
                else:
                    if "paymentId" in locals() and "purchaseId" in locals():
                        execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn)
                        execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchaseId + """';""", 'post', conn)
                
                return response
                # return "OK", 201
            except:

                response = {'message': "Payment process error."}
                return response, 500
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selection (Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            purchase_id = data['purchase_id']
            items_selected = "'[" + ", ".join([str(item).replace("'", "\"") for item in data['items']]) + "]'"
            delivery_day = data['delivery_day']
            sel_menu_date = data['menu_date']

            if data['is_addon']:
                res = execute("CALL new_addons_selected_uid();", 'get', conn)
            else:
                res = execute("CALL new_meals_selected_uid();", 'get', conn)
            if res['code'] != 280:
                print("*******************************************")
                print("* Cannot run the query to get a new \"selection_uid\" *")
                print("*******************************************")
                response['message'] = 'Internal Server Error.'
                return response, 500
            selection_uid = res['result'][0]['new_id']
            queries = [[
                        """
                        INSERT INTO addons_selected
                        SET selection_uid = '""" + selection_uid + """',
                            sel_purchase_id = '""" + purchase_id + """',
                            selection_time = '""" + getNow() + """',
                            sel_menu_date = '""" + sel_menu_date + """',
                            meal_selection = """ + items_selected + """,
                            delivery_day = '""" + delivery_day + """';
                        """
                        ],
                       [
                       """
                       INSERT INTO meals_selected
                       SET selection_uid = '""" + selection_uid + """',
                        sel_purchase_id = '""" + purchase_id + """',
                        selection_time = '""" + getNow() + """',
                        sel_menu_date = '""" + sel_menu_date + """',
                        meal_selection = """ + items_selected + """,
                        delivery_day = '""" + delivery_day + """';
                        """
                       ]]

            if data['is_addon'] == True:
                # write to addons selected table
                # need a stored function to get the new selection
                response = simple_post_execute(queries[0], ["ADDONS_SELECTED"], conn)
            else:
                response = simple_post_execute(queries[1], ["MEALS_SELECTED"], conn)
            if response[1] == 201:
                response[0]['selection_uid']= selection_uid
            return response
        except:
            if "selection_uid" in locals():
                execute("DELETE FROM addons_selected WHERE selection_uid = '" + selection_uid + "';", 'post', conn)
                execute("DELETE FROM meals_selected WHERE selection_uid = '" + selection_uid + "';", 'post', conn)
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)







class Refund_Calculator (Resource):
    def get(self):
        try:
            conn = connect()
            purchase_uid = request.args.get('purchase_uid')

            info_query = """
                       SELECT pur.*, pay.*, sub.*
                       FROM purchases pur, payments pay, subscription_items sub
                       WHERE pur.purchase_uid = pay.pay_purchase_uid
                           AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
                                                   FROM purchases WHERE purchase_uid = '""" + purchase_uid + """')
                           AND pur.purchase_uid = '""" + purchase_uid + """'
                           AND pur.purchase_status='ACTIVE';  
                       """
            info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
            if info_res[1] != 200:
                return {"message": "Internal Server Error"}, 500
            # Calculate refund
            try:
                refund_info = change_purchase().refund_calculator(info_res[0]['result'][0], conn)
            except:
                print("calculated error")
                return {"message": "Internal Server Error"}, 500
            return {'message': "Successful", 'result': [{"refund_amount": refund_info['refund_amount']}]}, 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)
    def refund_calf(self, p_uid):
        try:
            conn = connect()
            #purchase_uid = request.args.get('purchase_uid')

            info_query = """
                       SELECT pur.*, pay.*, sub.*
                       FROM purchases pur, payments pay, subscription_items sub
                       WHERE pur.purchase_uid = pay.pay_purchase_uid
                           AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
                                                   FROM purchases WHERE purchase_uid = '""" + p_uid + """')
                           AND pur.purchase_uid = '""" + p_uid + """'
                           AND pur.purchase_status='ACTIVE';  
                       """
            info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
            if info_res[1] != 200:
                return {"message": "Internal Server Error"}, 500
            # Calculate refund
            try:
                refund_info = Change_Purchase().refund_calculator(info_res[0]['result'][0], conn)
            except:
                print("calculated error")
                return {"message": "Internal Server Error"}, 500
            return {'message': "Successful", 'result': [{"refund_amount": refund_info['refund_amount']}]}, 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)



class Update_Delivery_Info (Resource):
    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            #print(data)
            [first_name, last_name, purchase_uid] = destructure(data, "first_name", "last_name", "purchase_uid")
            #print(first_name)
            [phone, email] = destructure(data, "phone", "email")
            [address, unit, city, state, zip] = destructure(data, 'address', 'unit', 'city', 'state', 'zip')
            [cc_num, cc_cvv, cc_zip, cc_exp_date] = [str(value) if value else None for value in destructure(data, "cc_num", "cc_cvv", "cc_zip", "cc_exp_date")]
            #print("1")
            #should re-calculator the longtitude and latitude before update address
            
            queries = ['''UPDATE M4ME.purchases 
                            SET delivery_first_name= "''' + first_name + '''",
                                delivery_last_name = "''' + last_name + '''",
                                delivery_phone_num = "''' + phone + '''",
                                delivery_email = "''' + email + '''", 
                                delivery_address = "''' + address + '''",
                                delivery_unit = "''' + unit + '''",
                                delivery_city = "''' + city + '''",
                                delivery_state = "''' + state + '''",
                                delivery_zip = "''' + zip + '''"
                            WHERE purchase_uid = "''' + purchase_uid + '";'
                    ,
                    ''' UPDATE M4ME.payments
                            SET cc_num = "''' + cc_num + '''",
                                cc_cvv = "''' + cc_cvv + '''",
                                cc_zip = "''' + cc_zip + '''",
                                cc_exp_date = "''' + cc_exp_date + '''"
                            WHERE pay_purchase_uid = "''' + purchase_uid + '";'

                    ]
            #print("3")
            res = simple_post_execute(queries, ["UPDATE PURCHASE'S INFO", "UPDATE PAYMENT'S INFO"], conn)
            if res[1] == 201:
                return {"message": "Update Successful"}, 200
            else:
                print("Something Wrong with the Update queries")
                return {"message": "Update Failed"}, 500
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

# ---------- ADMIN ENDPOINTS ----------------#
# admin endpoints start from here            #
#--------------------------------------------#
class Plans(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            #business_uid = request.args['business_uid']
            print("1")
            query = """
                    select * from subscription_items 
                    join discounts
                    where itm_business_uid = "200-000002";
                    """
            # query = """
            #         # ADMIN QUERY 5: PLANS 
            #         SELECT * FROM M4ME.subscription_items si 
            #         -- WHERE itm_business_uid = "200-000007"; 
            #         WHERE itm_business_uid = \'""" + business_uid + """\';
            #         """
            print("2")
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
# Endpoint for Create/Edit menu
class Menu (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 1: 
                    #  MEALS & MENUS: 1. CREATE/EDIT MENUS: SEE MENU FOR A PARTICULAR DAY  (ADD/DELETE MENU ITEM)
                    SELECT * FROM M4ME.menu
                    LEFT JOIN M4ME.meals
                        ON menu_meal_id = meal_uid
                    WHERE menu_date > ADDDATE(CURDATE(),-21) AND menu_date < ADDDATE(CURDATE(),45)
                    order by menu_type;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, Please try again later.")
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            menu_date = data['menu_date']
            menu_category = data['menu_category']
            menu_type = data['menu_type']
            meal_cat = data['meal_cat']
            menu_meal_id = data['menu_meal_id']
            default_meal = data['default_meal']
            delivery_days = "'[" + ", ".join([str(item) for item in data['delivery_days']]) + "]'"
            meal_price = data['meal_price']
            print("1")
            menu_uid = get_new_id("CALL new_menu_uid", "get_new_menu_ID", conn)
            if menu_uid[1] != 200:
                return menu_uid
            menu_uid = menu_uid[0]['result']

            query = """
                    INSERT INTO menu
                    SET menu_uid = '""" + menu_uid + """',
                        menu_date = '""" + menu_date + """',
                        menu_category = '""" + menu_category + """',
                        menu_type = '""" + menu_type + """',
                        meal_cat = '""" + meal_cat + """',
                        menu_meal_id = '""" + menu_meal_id + """',
                        default_meal = '""" + default_meal + """',
                        delivery_days = """ + delivery_days + """,
                        meal_price = '""" + meal_price + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = menu_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("1")
            menu_uid = data['menu_uid']
            menu_date = data['menu_date']
            menu_category = data['menu_category']
            menu_type = data['menu_type']
            meal_cat = data['meal_cat']
            menu_meal_id = data['menu_meal_id']
            default_meal = data['default_meal']
            print("2")
            #print(data["delivery_days"])
            #print([str(item) for item in data['delivery_days']])
            #print(type(data["delivery_days"]))
            #temp=  data["delivery_days"].split(",")
            delivery_days = data["delivery_days"]#''.join([letter for item in temp if letter.isalnum()])#data["delivery_days"].split(',')
            #print(delivery_days)
            meal_price = str(data['meal_price'])
            print("3")
            query = """
                    UPDATE menu
                    SET menu_date = '""" + menu_date + """',
                        menu_category = '""" + menu_category + """',
                        menu_type = '""" + menu_type + """',
                        meal_cat = '""" + meal_cat + """',
                        menu_meal_id = '""" + menu_meal_id + """',
                        default_meal = '""" + default_meal + """',
                        delivery_days = '""" + delivery_days + """',
                        meal_price = '""" + meal_price + """'
                    where menu_uid = '""" + menu_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response[1])
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = menu_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


    def delete(self):
        try:
            conn = connect()
            menu_uid = request.args['menu_uid']
            print("1")
            query = """
                    DELETE FROM menu WHERE menu_uid = '""" + menu_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class AllMenus (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 1: 
                    #  MEALS & MENUS: 1. CREATE/EDIT MENUS: SEE MENU FOR A PARTICULAR DAY  (ADD/DELETE MENU ITEM)
                    SELECT * FROM M4ME.menu
                    LEFT JOIN M4ME.meals
                        ON menu_meal_id = meal_uid
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, Please try again later.")
        finally:
            disconnect(conn)

class Delete_Menu_Specific (Resource):
    def delete(self):
        try:
            conn = connect()
            menu_uid = request.args['menu_uid']
            meal_uid = data['meal_uid']
            print("1")
            query = """
                    DELETE FROM menu WHERE menu_uid = '""" + menu_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




#working
class Meals (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    # ADMIN QUERY 2: MEAL OPTIONS
                    SELECT * FROM M4ME.meals m;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("1")
            meal_category = data['meal_category']
            meal_name = data['meal_name']
            meal_desc = data['meal_desc']
            meal_hint = "'" + data['meal_hint'] + "'" if data['meal_hint'] else 'NULL'
            print("2")
            meal_photo_url = data['meal_photo_url'] if data.get('meal_photo_url') is not None else 'NULL'
            #meal_photo_url = "'" + data['meal_photo_URL'] + "'" if data['meal_photo_URL'] else 'NULL'
            print("3")
            meal_calories = data['meal_calories']
            meal_protein = data['meal_protein']
            meal_carbs = data['meal_carbs']
            meal_fiber = data['meal_fiber']
            meal_sugar = data['meal_sugar']
            meal_fat = data['meal_fat']
            meal_sat = data['meal_sat']
            print("4")
            meal_uid = get_new_id("CALL new_meal_uid", "get_new_meal_ID", conn)
            if meal_uid[1] != 200:
                return meal_uid
            meal_uid = meal_uid[0]['result']
            print("5")
            query = """
                    INSERT INTO meals
                    SET meal_uid = '""" + meal_uid + """',
                        meal_category = '""" + meal_category + """',
                        meal_name = '""" + meal_name + """',
                        meal_desc = '""" + meal_desc + """',
                        meal_hint = """ + meal_hint + """,
                        meal_photo_url = """ + meal_photo_url + """,
                        meal_calories = '""" + meal_calories + """',
                        meal_protein = '""" + meal_protein + """',
                        meal_carbs = '""" + meal_carbs + """',
                        meal_fiber = '""" + meal_fiber + """',
                        meal_sugar = '""" + meal_sugar + """',
                        meal_fat = '""" + meal_fat + """',
                        meal_sat = '""" + meal_sat + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            #item_photo_url = helper_upload_meal_img(item_photo, key)
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = meal_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            meal_uid = data['meal_uid']
            meal_category = data['meal_category']
            meal_name = data['meal_name']
            meal_desc = data['meal_desc']
            meal_hint = "'" + data['meal_hint'] + "'" if data['meal_hint'] else 'NULL'
            meal_photo_url = "'" + data['meal_photo_URL'] + "'" if data['meal_photo_URL'] else 'NULL'
            meal_calories = data['meal_calories']
            meal_protein = data['meal_protein']
            meal_carbs = data['meal_carbs']
            meal_fiber = data['meal_fiber']
            meal_sugar = data['meal_sugar']
            meal_fat = data['meal_fat']
            meal_sat = data['meal_sat']

            query = """
                    UPDATE meals
                    SET meal_category = '""" + meal_category + """',
                        meal_name = '""" + meal_name + """',
                        meal_desc = '""" + meal_desc + """',
                        meal_hint = """ + meal_hint + """,
                        meal_photo_url = """ + meal_photo_url + """,
                        meal_calories = '""" + meal_calories + """',
                        meal_protein = '""" + meal_protein + """',
                        meal_carbs = '""" + meal_carbs + """',
                        meal_fiber = '""" + meal_fiber + """',
                        meal_sugar = '""" + meal_sugar + """',
                        meal_fat = '""" + meal_fat + """',
                        meal_sat = '""" + meal_sat + """'
                    WHERE meal_uid = '""" + meal_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['message'] = "Update successful."
            response[0]['meal_uid'] = meal_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    # delete meal endpoint
    # pass in parameter through the url i.e /api/v2/meals?meal_uid=840-010042
    def delete(self):
        try:
            conn = connect()
            meal_uid = request.args['meal_uid']
            query = """
                    DELETE FROM meals WHERE meal_uid = '""" + meal_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class create_update_meals(Resource):
    def post(self):
        lists={}
        items = {}
        try:
            conn = connect()
            # data = request.get_json(force=True)

            meal_category = request.form.get('meal_category')
            meal_name = request.form.get('meal_name') if request.form.get('meal_name') is not None else 'NULL'
            meal_desc = request.form.get('meal_desc') if request.form.get('meal_desc') is not None else 'NULL'
            meal_hint = request.form.get('meal_hint') if request.form.get('meal_hint') is not None else 'NULL'
            meal_photo_url = request.files.get('meal_photo_url') if request.files.get('meal_photo_url') is not None else 'NULL'
            #meal_photo_url = request.form.get('meal_photo_url') if request.form.get('meal_photo_url') is not None else 'NULL'
            meal_calories = request.form.get('meal_calories') if request.form.get('meal_calories') is not None else 'NULL'
            meal_protein = request.form.get('meal_protein') if request.form.get('meal_protein') is not None else 'NULL'
            meal_carbs = request.form.get('meal_carbs') if request.form.get('meal_carbs') is not None else 'NULL'
            meal_fiber = request.form.get('meal_fiber') if request.form.get('meal_fiber') is not None else 'NULL'
            meal_sugar = request.form.get('meal_sugar') if request.form.get('meal_sugar') is not None else 'NULL'
            meal_fat = request.form.get('meal_fat') if request.form.get('meal_fat') is not None else 'NULL'
            meal_sat = request.form.get('meal_sat') if request.form.get('meal_sat') is not None else 'NULL'
            #meal_notes = request.form.get('meal_notes') if request.form.get('meal_notes') is not None else 'NULL'
            #taxable = request.form.get('taxable') if request.form.get('taxable') is not None else 'NULL'
            meal_uid = get_new_id("CALL new_meal_uid", "get_new_meal_ID", conn)
            if meal_uid[1] != 200:
                return meal_uid
            meal_uid = meal_uid[0]['result']
            print("1")
            TimeStamp_test = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            key =  "items/" + str(meal_uid) + "_" + TimeStamp_test
            print(key)
            meal_photo = helper_upload_meal_img(meal_photo_url, key)
            print("2")
            print(meal_uid)
            #print(meal_notes)
            # INSERT query
            query = """
                    INSERT INTO meals
                    SET meal_uid = '""" + meal_uid + """',
                        meal_category = '""" + meal_category + """',
                        meal_name = '""" + meal_name + """',
                        meal_desc = '""" + meal_desc + """',
                        meal_hint = '""" + meal_hint + """',
                        meal_photo_url = '""" + meal_photo + """',
                        meal_calories = '""" + meal_calories + """',
                        meal_protein = '""" + meal_protein + """',
                        meal_carbs = '""" + meal_carbs + """',
                        meal_fiber = '""" + meal_fiber + """',
                        meal_sugar = '""" + meal_sugar + """',
                        meal_fat = '""" + meal_fat + """',
                        meal_sat = '""" + meal_sat + """';
                    """
            print("2.5")
            response = simple_post_execute([query], [__class__.__name__], conn)
            # response = execute(query, 'post', conn)
            print("3")
            #meal_photo = helper_upload_meal_img(meal_photo_url, key)
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = meal_uid
            print("4")
            # lists=get_all_s3_keys(mtyd)
            # print("ending sequence")
            # return response, lists
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



    def put(self):
        lists = {}
        items = {}
        try:
            conn = connect()
            # data = request.get_json(force=True)

            meal_category = request.form.get('meal_category')
            meal_name = request.form.get('meal_name') if request.form.get('meal_name') is not None else 'NULL'
            meal_desc = request.form.get('meal_desc') if request.form.get('meal_desc') is not None else 'NULL'
            meal_hint = request.form.get('meal_hint') if request.form.get('meal_hint') is not None else 'NULL'
            meal_photo_url = request.files.get('meal_photo_url') if request.files.get('meal_photo_url') is not None else 'NULL'
            #meal_photo_url = request.form.get('meal_photo_url') if request.form.get('meal_photo_url') is not None else 'NULL'
            meal_calories = request.form.get('meal_calories') if request.form.get('meal_calories') is not None else 'NULL'
            meal_protein = request.form.get('meal_protein') if request.form.get('meal_protein') is not None else 'NULL'
            meal_carbs = request.form.get('meal_carbs') if request.form.get('meal_carbs') is not None else 'NULL'
            meal_fiber = request.form.get('meal_fiber') if request.form.get('meal_fiber') is not None else 'NULL'
            meal_sugar = request.form.get('meal_sugar') if request.form.get('meal_sugar') is not None else 'NULL'
            meal_fat = request.form.get('meal_fat') if request.form.get('meal_fat') is not None else 'NULL'
            meal_sat = request.form.get('meal_sat') if request.form.get('meal_sat') is not None else 'NULL'
            #taxable = request.form.get('taxable') if request.form.get('taxable') is not None else 'NULL'
            meal_uid = request.form.get('meal_sat') 
            #meal_notes = request.form.get('meal_notes') if request.form.get('meal_notes') is not None else 'NULL'
            print("1")
            TimeStamp_test = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            key =  "items/" + str(meal_uid) + "_" + TimeStamp_test
            print(key)
            meal_photo = helper_upload_meal_img(meal_photo_url, key)
            print("2")
            print(meal_uid)
            print(meal_notes)
            # INSERT query
            query = """
                    Update meals
                    SET 
                        meal_category = '""" + meal_category + """',
                        meal_name = '""" + meal_name + """',
                        meal_desc = '""" + meal_desc + """',
                        meal_hint = '""" + meal_hint + """',
                        meal_photo_url = '""" + meal_photo + """',
                        meal_calories = '""" + meal_calories + """',
                        meal_protein = '""" + meal_protein + """',
                        meal_carbs = '""" + meal_carbs + """',
                        meal_fiber = '""" + meal_fiber + """',
                        meal_sugar = '""" + meal_sugar + """',
                        meal_fat = '""" + meal_fat + """',
                        meal_sat = '""" + meal_sat + """'
                    where meal_uid = '""" + meal_uid + """';
                    """
            print("2.5")
            response = simple_post_execute([query], [__class__.__name__], conn)
            # response = execute(query, 'post', conn)
            print("3")
            #meal_photo = helper_upload_meal_img(meal_photo_url, key)
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = meal_uid
            lists=get_all_s3_keys(mtyd)
            return response, lists
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)







class Recipes (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 3: 
                    #  MEALS & MENUS  4. EDIT MEAL RECIPE: 
                    SELECT * FROM M4ME.meals
                    LEFT JOIN M4ME.recipes
                        ON meal_uid = recipe_meal_id
                    LEFT JOIN M4ME.ingredients
                        ON recipe_ingredient_id = ingredient_uid
                    LEFT JOIN M4ME.conversion_units
                        ON recipe_measure_id = measure_unit_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

class Delete_Recipe_Specific (Resource):
    def delete(self):
        try:
            conn = connect()
            #data = request.get_json(force=True)
            recipe_uid = request.args['recipe_uid']
            print("1")
            query = """
                    DELETE FROM recipes WHERE recipe_uid = '""" + recipe_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



#working ingredient here
class Ingredients (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 4: 
                    #  MEALS & MENUS  5. CREATE NEW INGREDIENT:
                    SELECT DISTINCT ingredient_uid, ingredient_desc FROM M4ME.ingredients
                    LEFT JOIN M4ME.inventory
                        ON ingredient_uid = inventory_ingredient_id
                    LEFT JOIN M4ME.conversion_units
                        ON inventory_measure_id = measure_unit_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            #package_measure = data['package_measure']
            package_unit = data['package_unit']
            package_cost = data['package_cost']
            #inventory_date = data['inventory_date']
            #inventory_qty = data['inventory_qty']
            #inventory_measure_id = data['inventory_measure_id']
            print("0")
            
            unit_cost = str(float(package_cost)/float(package_size))
            print(unit_cost)
            #inventory_location = data['inventory_location']
            ingredient_uid_request = get_new_id("CALL new_ingredient_uid();", "Get_New_Ingredient_uid", conn)

            if ingredient_uid_request[1]!= 200:
                return ingredient_uid_request
            ingredient_uid = ingredient_uid_request[0]['result']
            query = """
                    INSERT INTO ingredients
                    SET ingredient_uid = '""" + ingredient_uid + """',
                        ingredient_desc = '""" + ingredient_desc + """',
                        package_size = '""" + package_size + """',
                        package_unit = '""" + package_unit + """',
                        package_cost = '""" + package_cost + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response)
            if response[1] != 201:
                return response
            response[0]['ingredient_uid'] = ingredient_uid

            query2 = "CALL M4ME.new_inventory_uid"
            inventory_uid_query = execute(query2, 'get', conn)
            inventory_uid = inventory_uid_query['result'][0]['new_id']
            print("2")
            print(inventory_uid)
            query1 = """
                    INSERT INTO inventory
                    SET inventory_uid = \'""" + inventory_uid + """\',
                        inventory_ingredient_id = \'""" + ingredient_uid + """\',
                        inventory_date = curdate(),
                        inventory_qty = 0,
                        inventory_measure_id = \'""" + package_unit + """\',
                        unit_cost = \'""" + unit_cost + """\',
                        inventory_location = "CA";
                    """
            print("3")
            response1 = simple_post_execute([query1], [__class__.__name__], conn)
            print(response1)
            if response[1] != 201:
                return response1
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            ingredient_uid = data['ingredient_uid']
            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            #package_measure = data['package_measure']
            package_unit = data['package_unit']
            package_cost = data['package_cost']

            query = """
                    UPDATE ingredients
                    SET 
                        ingredient_desc = '""" + ingredient_desc + """',
                        package_size = '""" + package_size + """',
                        package_unit = '""" + package_unit + """',
                        package_cost = '""" + package_cost + """'
                    WHERE ingredient_uid = '""" + ingredient_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            ingredient_uid = request.args['ingredient_uid']

            query = """
                    DELETE FROM ingredients WHERE ingredient_uid = '""" + ingredient_uid + """';
                    """
            print(query)
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Measure_Unit (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 5: 
                    #  MEALS & MENUS  6. CREATE NEW MEASURE UNIT: 
                    SELECT * FROM M4ME.conversion_units;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            type = data['type']
            recipe_unit = data['recipe_unit']
            conversion_ratio = data['conversion_ratio']
            common_unit = data['common_unit']

            measure_unit_uid_request = get_new_id("CALL new_measure_unit_uid();", "Get_New_Measure_Unit_uid", conn)

            if measure_unit_uid_request[1]!= 200:
                return measure_unit_uid_request
            measure_unit_uid = measure_unit_uid_request[0]['result']

            query = """
                    INSERT INTO conversion_units
                    SET measure_unit_uid = '""" + measure_unit_uid + """',
                        type = '""" + type + """',
                        recipe_unit = '""" + recipe_unit + """',
                        conversion_ratio = '""" + conversion_ratio + """',
                        common_unit = '""" + common_unit + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['measure_unit_uid'] = measure_unit_uid
            return response
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            measure_unit_uid = data['measure_unit_uid']
            type = data['type']
            recipe_unit = data['recipe_unit']
            conversion_ratio = data['conversion_ratio']
            common_unit = data['common_unit']

            query = """
                    UPDATE conversion_units
                    SET type = '""" + type + """',
                        recipe_unit = '""" + recipe_unit + """',
                        conversion_ratio = '""" + conversion_ratio + """',
                        common_unit = '""" + common_unit + """'
                    WHERE measure_unit_uid = '""" + measure_unit_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            ingredient_uid = request.args['ingredient_uid']

            query = """
                    DELETE FROM conversion_units WHERE measure_unit_uid = '""" + measure_unit_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Coupons(Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 7: 
                    # PLANS & COUPONS  2. SHOW ALL COUPONS
                    SELECT * FROM M4ME.coupons;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            coupon_id = data['coupon_id']
            valid = data['valid']
            discount_percent = data['discount_percent']
            discount_amount = data['discount_amount']
            discount_shipping = data['discount_shipping']
            expire_date = data['expire_date']
            limits = data['limits']
            notes = data['notes']
            num_used = data['num_used'] if data.get("num_used") else 0
            recurring = data['recurring']
            email_id = "'" + data['email_id'] + "'" if data['email_id'] else 'NULL'
            cup_business_uid = data['cup_business_uid']

            coupon_uid_request = get_new_id("CALL new_coupons_uid();", "Get_New_Coupons_uid", conn)
            if coupon_uid_request[1]!= 200:
                return coupon_uid_request

            coupon_uid = coupon_uid_request[0]['result']
            query = """
                    INSERT INTO coupons
                    SET coupon_uid = '""" + coupon_uid + """',
                        coupon_id = '""" + coupon_id + """',
                        valid = '""" + valid + """',
                        discount_percent = '""" + discount_percent + """',
                        discount_amount = '""" + discount_amount + """',
                        discount_shipping = '""" + discount_shipping + """',
                        expire_date = '""" + expire_date + """',
                        limits = '""" + limits + """',
                        notes = '""" + notes + """',
                        num_used = '""" + str(num_used) + """',
                        recurring = '""" + recurring + """',
                        email_id = """ + email_id + """,
                        cup_business_uid = '""" + cup_business_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['coupon_uid'] = coupon_uid
            return response
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            coupon_uid = data['coupon_uid']
            coupon_id = data['coupon_id']
            valid = data['valid']
            discount_percent = str(data['discount_percent'])
            discount_amount = str(data['discount_amount'])
            discount_shipping = str(data['discount_shipping'])
            expire_date = data['expire_date']
            limits = data['limits']
            notes = data['notes']
            num_used = data['num_used'] if data.get("num_used") else 0
            recurring = data['recurring']
            email_id = "'" + data['email_id'] + "'" if data['email_id'] else 'NULL'
            cup_business_uid = data['cup_business_uid']
            print("1")
            query = """
                    UPDATE coupons
                    SET coupon_id = '""" + coupon_id + """',
                        valid = '""" + valid + """',
                        discount_percent = '""" + discount_percent + """',
                        discount_amount = '""" + discount_amount + """',
                        discount_shipping = '""" + discount_shipping + """',
                        expire_date = '""" + expire_date + """',
                        limits = '""" + limits + """',
                        notes = '""" + notes + """',
                        num_used = '""" + str(num_used) + """',
                        recurring = '""" + recurring + """',
                        email_id = """ + email_id + """,
                        cup_business_uid = '""" + cup_business_uid + """'
                    WHERE coupon_uid = '""" + coupon_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print("2")
            print(response)
            if response[1] != 201:
                return response
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            coupon_uid = request.args['coupon_uid']

            query = """
                    DELETE FROM coupons WHERE coupon_uid = '""" + coupon_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class CouponDetails(Resource):
    def get(self, coupon_id):
        response = {}
        items = {}
        try:
            conn = connect()
            query = """
                    SELECT * FROM M4ME.coupons
                    WHERE coupon_uid = \'""" + coupon_id + """\'
                    """
            items = execute(query, 'get', conn)

            response['message'] = 'CouponDetails successful'
            response['result'] = items
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

        # http://localhost:4000/api/v2/couponDetails/Jane6364
        # https://tsx3rnuidi.execute-api.us-west-1.amazonaws.com/dev/api/v2/couponDetails/Jane6364


    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            coupon_uid = data['coupon_uid']
            num_used = (data['num_used'])
            print("coupon_uid", coupon_uid)
            print("num_used",  num_used)



            query = '''
                    UPDATE M4ME.coupons
                    SET num_used = \'''' + str(num_used) + '''\'
                    WHERE coupon_uid = \'''' + str(coupon_uid) + '''\';
                    '''
            items = execute(query,'post',conn)

            response['message'] = 'CouponDetails POST successful'
            response['result'] = items
            return response, 200
        except:
            raise BadRequest('Q3 POST Request failed, please try again later.')
        finally:
            disconnect(conn)






class Ordered_By_Date(Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 9: 
                    #  ORDERS & INGREDIENTS  1. HOW MUCH HAS BEEN ORDERED BY DATE
                    #  LIKE VIEW E BUT WITH SPECIFIC COLUMNS CALLED OUT
                    SELECT d_menu_date,
                        jt_item_uid,
                        jt_name,
                        sum(jt_qty)
                    FROM(
                        SELECT *
                        FROM M4ME.final_meal_selection AS jot,
                        JSON_TABLE (jot.final_combined_selection, '$[*]' 
                            COLUMNS (
                                    jt_id FOR ORDINALITY,
                                    jt_item_uid VARCHAR(255) PATH '$.item_uid',
                                    jt_name VARCHAR(255) PATH '$.name',
                                    jt_qty INT PATH '$.qty',
                                    jt_price DOUBLE PATH '$.price')
                                ) AS jt)
                        AS total_ordered
                    GROUP BY d_menu_date, jt_name;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Ingredients_Need (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 10: 
                    #  ORDERS & INGREDIENTS    2. WHAT INGREDIENTS NEED TO BE PURCHASED BY DATE
                    SELECT -- *,
                        d_menu_date,
                        ingredient_uid,
                        ingredient_desc,
                        sum(qty_needed), 
                        units
                    FROM(
                    SELECT *,
                        recipe_ingredient_qty / conversion_ratio AS qty_needed,
                        common_unit AS units
                    FROM (
                        SELECT d_menu_date,
                            jt_item_uid,
                            jt_name,
                            sum(jt_qty)
                        FROM(
                            SELECT *
                            FROM M4ME.final_meal_selection AS jot,
                            JSON_TABLE (jot.final_combined_selection, '$[*]' 
                                COLUMNS (
                                        jt_id FOR ORDINALITY,
                                        jt_item_uid VARCHAR(255) PATH '$.item_uid',
                                        jt_name VARCHAR(255) PATH '$.name',
                                        jt_qty INT PATH '$.qty',
                                        jt_price DOUBLE PATH '$.price')
                                    ) AS jt)
                                    AS total_ordered
                        GROUP BY d_menu_date, jt_name) 
                        AS ordered
                    LEFT JOIN M4ME.recipes
                        ON jt_item_uid = recipe_meal_id
                    LEFT JOIN M4ME.ingredients
                        ON recipe_ingredient_id = ingredient_uid
                    LEFT JOIN M4ME.conversion_units
                        ON recipe_measure_id = measure_unit_uid)
                        AS ing
                    GROUP BY d_menu_date, ingredient_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)











class Edit_Menu(Resource):
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(""" select meal_name from M4ME.meals;""", 'get', conn)
            items2 = execute(""" select * from M4ME.menu;""", 'get', conn)

            response['message'] = 'Request successful.'
            response['result'] = items
            response['result2'] = items2

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("connected")
            menu_date = data['menu_date']
            menu = data['menu']
            print("data received")
            print(menu_date)
            print(menu)
            # items['delete_menu'] = execute("""delete from menu
            #                                             where menu_date = \'""" + str(menu_date) + """\';
            #                                                 """, 'post', conn)
            # print("menu deleted")

            i = 0
            for eachitem in data['menu']:
                menu_category = eachitem['menu_category'] if eachitem['menu_category'] else "null"
                menu_type = eachitem['menu_type'] if eachitem['menu_type'] else "null"
                meal_cat = eachitem['meal_cat'] if eachitem['meal_cat'] else "null"
                meal_name = eachitem['meal_name'] if eachitem['meal_name'] else "null"
                default_meal = eachitem['default_meal'] if eachitem['default_meal'] else "null" 
                menu_uid = get_new_id("CALL new_menu_uid", "get_new_menu_ID", conn)
                print(menu_category)
                print(menu_type)
                print(meal_cat)
                print(meal_name)
                print(default_meal)

                query = """insert into M4ME.menu (menu_uid, menu_date, menu_category, menu_type, meal_cat, menu_meal_id, default_meal) 
                        values 
                        (\'""" + menu_uid + """\'
                        \'""" + menu_date + """\',
                        \'""" + menu_category + """\',
                        \'""" + menu_type + """\',
                        \'""" + meal_cat + """\',
                        (select meal_uid from meals where meal_name = \'""" + meal_name + """\'),
                        \'""" + default_meal + """\');"""
                print(query)
                items = execute(query,'post',conn)
                print(items)
                i += 1
            print("done")
                
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)












class Edit_Meal(Resource):
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()
            items = execute(""" select * from meals;""", 'get', conn)

            response['message'] = 'successful'
            response['result'] = items
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            meal = data["meal"]

            mealId = data['mealId']
            meal_category = data['meal_category']
            meal_name = data['meal_name']
            meal_desc = data['meal_desc']
            meal_hint = data['meal_hint']
            meal_photo_URL = data['meal_photo_URL']
            # extra_meal_price = data['extra_meal_price']
            meal_calories = data['meal_calories']
            meal_protein = data['meal_protein']
            meal_carbs = data['meal_carbs']
            meal_fiber = data['meal_fiber']
            meal_sugar = data['meal_sugar']
            meal_fat = data['meal_fat']
            meal_sat = data['meal_sat']
            i = 0
            for eachitem in data['meal']:
                mealId = eachitem['mealId'] if eachitem['mealId'] else "null"
                meal_category = eachitem['meal_category']
                meal_name = eachitem['meal_name']
                meal_desc = eachitem['meal_desc']
                meal_hint = eachitem['meal_hint']
                meal_photo_URL = eachitem['meal_photo_URL']
                meal_calories = eachitem['meal_calories']
                meal_protein = eachitem['meal_protein']
                meal_carbs = eachitem['meal_carbs']
                meal_fiber = eachitem['meal_fiber']
                meal_sugar = eachitem['meal_sugar']
                meal_fat = eachitem['meal_fat']
                meal_sat = eachitem['meal_sat']
            print(data)
            print("Items read...")
            query = """
                        insert into M4ME.menu 
                        values 
                        (\'""" + menu_date + """\',
                        \'""" + menu_category + """\',
                        \'""" + menu_type + """\',
                        \'""" + meal_cat + """\',
                        (select meal_id from meals where meal_name = \'""" + meal_name + """\'),
                        \'""" + default_meal + """\');
                    """
            
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn) 












class MealCreation(Resource):
    def listIngredients(self, result):
        response = {}
        print("1")
        for meal in result:
            key = meal['meal_id']
            if key not in response:
                response[key] = {}
                response[key]['meal_name'] = meal['meal_name']
                response[key]['ingredients'] = []
            ingredient = {}
            ingredient['name'] = meal['ingredient_desc']
            ingredient['qty'] = meal['recipe_ingredient_qty']
            ingredient['units'] = meal['recipe_unit']
            ingredient['ingredient_id'] = meal['ingredient_id']
            ingredient['measure_id'] = meal['recipe_measure_id']
            response[key]['ingredients'].append(ingredient)

        return response
        print("2")
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            query = """SELECT
                            m.meal_id,
                            m.meal_name,
                            ingredient_id,
                            ingredient_desc,
                            recipe_ingredient_qty,
                            recipe_unit,
                            recipe_measure_id
                            FROM
                            meals m
                            left JOIN
                            recipes r
                            ON
                            recipe_meal_id = meal_id
                            left JOIN
                            ingredients
                            ON
                            ingredient_id = recipe_ingredient_id
                            left join
                            conversion_units
                            ON                    
                            recipe_measure_id = measure_unit_uid
                            order by recipe_meal_id;"""

            sql = execute(query, 'get', conn)

            items = self.listIngredients(sql['result'])

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        # response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            # Post JSON needs to be in this format
                    #   data = {
                    #       'meal_id': '700-000001',
                    #       'ingredient_id': '110-000002',
                    #       'ingredient_qty': 3,
                    #       'measure_id': '130-000004'
                    #   }
            #print("1")

            # get_user_id_query = "CALL new_customer_uid();"
            # print(get_user_id_query)
            # NewUserIDresponse = execute(get_user_id_query, 'get', conn)
            # print(NewUserIDresponse)
            get_recipe_query = "CALL new_recipe_uid();"
            #print("2")
            #print(get_recipe_query)
            recipe_uid = execute(get_recipe_query, 'get', conn)
            #print(recipe_uid)
            NewRecipeID = recipe_uid['result'][0]['new_id']
            #print(NewRecipeID)

            #print("5")
            query = """
                INSERT INTO recipes 
                SET
                    recipe_uid = \'""" + NewRecipeID + """\',
                    recipe_meal_id = \'""" + data['meal_id'] + """\',
                    recipe_ingredient_id = \'""" + data['ingredient_id'] + """\',
                    recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
                    recipe_measure_id = \'""" + data['measure_id'] + """\'

                ON DUPLICATE KEY UPDATE
                    recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
                    recipe_measure_id = \'""" + data['measure_id'] + "\';"
            #print("6")
            #print(data)
            #original code
            # query = """
            #     INSERT INTO recipes (
            #         recipe_meal_id,
            #         recipe_ingredient_id,
            #         recipe_ingredient_qty,
            #         recipe_measure_id )
            #     VALUES (
            #         \'""" + data['meal_id'] + """\',
            #         \'""" + data['ingredient_id'] + """\',
            #         \'""" + data['ingredient_qty'] + """\',
            #         \'""" + data['measure_id'] + """\')
            #     ON DUPLICATE KEY UPDATE
            #         recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
            #         recipe_measure_id = \'""" + data['measure_id'] + "\';"
            #print("7")
            response = simple_post_execute([query], [__class__.__name__], conn)
            #print("8")
            #items = self.listIngredients(sql['result'])
            #print(items)
            response = 'Request successful.'
            #print("9")
            
            #response['result'] = items
            #print("10")
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)










class Edit_Recipe(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            meal_id = data['meal_id']
            meal_name = data['meal_name']
            ingredients = data['ingredients']

            items['delete_ingredients'] = execute("""delete from recipes
                                                        where recipe_meal_id = \'""" + str(meal_id) + """\';
                                                            """, 'post', conn)

            i = 0
            for eachIngredient in data['ingredients']:
                name = ingredients[i]['name']
                qty = ingredients[i]['qty']
                units = ingredients[i]['units']
                ingredient_id = ingredients[i]['ingredient_id']
                measure_id = ingredients[i]['measure_id']
                print(name)
                print(qty)
                print(units)
                print(ingredient_id)
                print(measure_id)
                print(meal_id)
                print(meal_name)
                print("************************")

                items['new_ingredients_insert'] = execute(""" INSERT INTO recipes (
                                                            recipe_meal_id, recipe_ingredient_id, recipe_ingredient_qty, 
                                                            recipe_measure_id
                                                            ) 
                                                            VALUES (
                                                            \'""" + str(meal_id) + """\',
                                                            \'""" + str(ingredient_id) + """\',
                                                            \'""" + str(qty) + """\',
                                                            \'""" + str(measure_id) + """\'
                                                            );
                                                            """, 'post', conn)
                i += 1

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)










class Add_New_Ingredient(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            ingredient_measure_id = data['ingredient_measure_id']
            ingredient_cost = data['ingredient_cost']

            ingredientIdQuery = execute(
                """CALL get_new_ingredient_id();""", 'get', conn)
            ingredientId = ingredientIdQuery['result'][0]['new_id']
            items['new_ingredient_insert'] = execute(""" INSERT INTO ingredients (
                                                                ingredient_id, ingredient_desc, package_size,ingredient_measure_id,ingredient_cost, ingredient_measure
                                                                ) 
                                                                SELECT \'""" + str(ingredientId) + """\', \'""" + str(ingredient_desc) + """\',
                                                                \'""" + str(package_size) + """\',\'""" + str(ingredient_measure_id) + """\',
                                                                \'""" + str(ingredient_cost) + """\', mu.recipe_unit 
                                                                FROM ptyd_conversion_units mu
                                                                WHERE measure_unit_id=\'""" + str(ingredient_measure_id) + """\';
                                                                """, 'post', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(""" SELECT
                                *
                                FROM
                                ptyd_ingredients;""", 'get', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)











class Add_Meal_plan(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            print("connection done...")
            data = request.get_json(force=True)
            print("data collected...")
            print(data)
            meal_planIdQuery = execute("""CALL get_new_meal_plan_id();""", 'get', conn)
            print("meal_Plan_id called..")
            mealPlanId = meal_planIdQuery['result'][0]['new_id']
            print("new_meal_plan_id created...")

            meal_plan_desc = data['meal_plan_desc']
            payment_frequency = data['payment_frequency']
            photo_URL = data['photo_URL']
            plan_headline = data['plan_headline']
            plan_footer = data['plan_footer']
            num_meals = data['num_meals']
            meal_weekly_price = data['meal_weekly_price']
            meal_plan_price = data['meal_plan_price']
            meal_shipping = data['meal_shipping']

            print("Items read...")
            items['new_meal_insert'] = execute("""INSERT INTO subscription_items  ( 	
                                                    item_uid,item_desc,payment_frequency,item_photo,info_headline,
                                                    info_footer,num_items,info_weekly_price,item_price,shipping 
                                                    ) 
                                                    VALUES ( 	
                                                    \'""" + str(mealPlanId) + """\',\'""" + str(meal_plan_desc) + """\',
                                                    \'""" + str(payment_frequency) + """\',\'""" + str(photo_URL) + """\',
                                                    \'""" + str(plan_headline) + """\',\'""" + str(plan_footer) + """\',
                                                    \'""" + str(num_meals) + """\',\'""" + str(meal_weekly_price) + """\',
                                                    \'""" + str(meal_plan_price) + """\',\'""" + str(meal_shipping) + """\'
                                                    );""", 'post', conn)

            print("meal_plan_inserted...")

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)






class Profile(Resource):
    # Fetches ALL DETAILS FOR A SPECIFIC USER

    def get(self, id):
    #def get(self):
        response = {}
        items = {}
        #customer_uid = request.args['customer_uid']
        print("user_id: ", id)
        try:
            conn = connect()
            query = """
                    SELECT *
                    FROM M4ME.customers c
                    WHERE customer_uid = \'""" + id + """\'
                    """
            items = execute(query, 'get', conn)
            if items['result']:

                items['message'] = 'Profile Loaded successful'
                items['result'] = items['result']
                items['code'] = 200
                return items
            else:
                items['message'] = "Customer UID doesn't exists"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class UpdateProfile(Resource):
    def post(self):
            response = {}
            item = {}
            try:
                conn = connect()
                data = request.get_json(force=True)

                #query = "CALL M4ME.new_profile"
                #new_profile_query = execute(query, 'get', conn)
                #new_profile = newPaymentUID_query['result'][0]['new_id']

                uid= data['uid']
                f_name= data['first_name']
                l_name= data['last_name']
                phone= data['phone']
                email= data['email']
                address= data['address']
                unit= data['unit']
                city= data['city']
                state= data['state']
                zip_code= data['zip']
                notification= data['noti']
                print(data)

                customer_insert_query = [""" 
                                    UPDATE M4ME.customers
                                    SET
                                    customer_first_name = \'""" + f_name + """\',
                                    customer_last_name = \'""" + l_name + """\',
                                    customer_phone_num = \'""" + phone + """\',
                                    customer_email = \'""" + email + """\',
                                    customer_address = \'""" + address + """\',
                                    customer_unit = \'""" + unit + """\',
                                    customer_city = \'""" + city + """\',
                                    customer_state = \'""" + state + """\',
                                    customer_zip = \'""" + zip_code + """\',
                                    cust_notification_approval = \'""" + notification + """\'
                                    WHERE customer_uid =\'""" + uid + """\';
                                """]


                #print(customer_insert_query)
                item = execute(customer_insert_query[0], 'post', conn)
                print(item)
                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'Profile info updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

                return item

            except:
                print("Error happened while inserting in customer table")
                raise BadRequest('Request failed, please try again later.')
            finally:
                disconnect(conn)
                print('process completed')





class access_refresh_update(Resource):

    def post(self):

        try:
            conn = connect()
            data = request.get_json(force=True)
            query = """
                    UPDATE M4ME.customers SET user_access_token = \'""" + data['access_token'] + """\', user_refresh_token = \'""" + data['refresh_token'] + """\', social_timestamp =  \'""" + data['social_timestamp'] + """\' WHERE (customer_uid = \'""" + data['uid'] + """\'); ;
                    """
            print(query)
            items = execute(query, 'post', conn)
            if items['code'] == 281:
                items['message'] = 'Access and refresh token updated successfully'
                print(items['code'])
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
                items['code'] = 400
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



# class access_refresh_update(Resource):

#     def post(self):

#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             query = """
#                     UPDATE M4ME.customers SET 
#                     user_access_token = \'""" + data['access_token'] + """\', 
#                     user_refresh_token = \'""" + data['refresh_token'] + """\', 
#                     social_timestamp =  \'""" + data['social_timestamp'] + """\' 
#                     WHERE (customer_uid = \'""" + data['uid'] + """\'); ;
#                     """
#             print(query)
#             items = execute(query, 'post', conn)
#             if items['code'] == 281:
#                 items['message'] = 'Access and refresh token updated successfully'
#                 print(items['code'])
#                 items['code'] = 200
#             else:
#                 items['message'] = 'Check sql query'
#                 items['code'] = 400


#             return items

#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)




# class token_fetch_update (Resource):

#     def post(self, action):
#         items = {}
#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             email = data['email']
#             print(data)

#             if action == 'get':
#                 query = """
#                         SELECT *
#                         FROM M4ME.customers c
#                         WHERE customer_email = \'""" + email + """\';
#                         """
#                 items = execute(query, 'get', conn)

#                 if items['result']:

#                     items['message'] = 'Tokens recieved successful'
#                     items['result'] = items['result']
#                     items['code'] = 200
#                     return items
#                 else:
#                     items['message'] = "Email doesn't exists"
#                     items['result'] = items['result']
#                     items['code'] = 404
#                     return items
#             elif action == 'update':
#                 query = """
#                         UPDATE M4ME.customers 
#                         SET  
#                         user_access_token = \'""" + data['user_access_token'] + """\', 
#                         user_refresh_token = \'""" + data['user_refresh_token'] + """\',
#                         mobile_access_token = \'""" + data['mobile_access_token'] + """\', 
#                         mobile_refresh_token = \'""" + data['mobile_refresh_token'] + """\', 
#                         social_timestamp = DATE_ADD(social_timestamp , INTERVAL 14 DAY)
#                         WHERE customer_email = \'""" + email + """\';
#                         """
#                 print(query)
#                 items = execute(query, 'post', conn)
#                 print(items)

#                 if items['code'] == 281:

#                     items['message'] = 'Tokens and timestamp updated successful'
#                     items['result'] = items['result']
#                     items['code'] = 200
#                     return items
#                 else:
#                     items['message'] = "Email doesn't exists"
#                     items['result'] = items['result']
#                     items['code'] = 404
#                     return items

#             else:
#                 items['code'] = 400
#                 items['message'] = 'Select proper option'


#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)



class token_fetch_update (Resource):

    def post(self, action):
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            uid = data['uid']
            print(data)

            if action == 'get':
                query = """
                        SELECT *
                        FROM M4ME.customers c
                        WHERE customer_uid = \'""" + uid + """\';
                        """
                items = execute(query, 'get', conn)

                if items['result']:

                    items['message'] = 'Tokens recieved successful'
                    items['result'] = items['result']
                    items['code'] = 200
                    return items
                else:
                    items['message'] = "UID doesn't exists"
                    items['result'] = items['result']
                    items['code'] = 404
                    return items

            elif action == 'update_mobile':
                query = """
                        UPDATE M4ME.customers 
                        SET  
                        mobile_access_token = \'""" + data['mobile_access_token'] + """\', 
                        mobile_refresh_token = \'""" + data['mobile_refresh_token'] + """\', 
                        social_timestamp = DATE_ADD(social_timestamp , INTERVAL 14 DAY)
                        WHERE customer_uid = \'""" + uid + """\';
                        """
                print(query)
                items = execute(query, 'post', conn)
                print(items)
                print('code------', items['code'])

                if items['code'] == 281:

                    items['message'] = 'Tokens and timestamp updated successful'
                    items['code'] = 200
                    return items
                else:
                    items['message'] = "UID doesn't exists"
                    items['result'] = items['result']
                    items['code'] = 404
                    return items

            elif action == 'update_web':
                query = """
                        UPDATE M4ME.customers 
                        SET  
                        user_access_token = \'""" + data['user_access_token'] + """\', 
                        user_refresh_token = \'""" + data['user_refresh_token'] + """\',
                        social_timestamp = DATE_ADD(social_timestamp , INTERVAL 14 DAY)
                        WHERE customer_uid = \'""" + uid + """\';
                        """
                print(query)
                items = execute(query, 'post', conn)
                print(items)
                print('code------', items['code'])

                if items['code'] == 281:

                    items['message'] = 'Tokens and timestamp updated successful'
                    items['code'] = 200
                    return items
                else:
                    items['message'] = "UID doesn't exists"
                    items['result'] = items['result']
                    items['code'] = 404
                    return items

            else:
                items['code'] = 400
                items['message'] = 'Select proper option'


        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class customer_infos(Resource):
    def get(self):
            response = {}
            item = {}
            try:
                conn = connect()
                print("1")
                #data = request.get_json(force=True)
                print("2")
                #query = "CALL M4ME.new_profile"
                #new_profile_query = execute(query, 'get', conn)
                #new_profile = newPaymentUID_query['result'][0]['new_id']

                # uid= data['uid']
                # f_name= data['first_name']
                # l_name= data['last_name']
                # phone= data['phone']
                # email= data['email']
                # address= data['address']
                # unit= data['unit']
                # city= data['city']
                # state= data['state']
                # zip_code= data['zip']
                # notification= data['noti']

                query = """ 
                            select customer_uid, 
                                customer_first_name, 
                                customer_last_name, 
                                customer_phone_num, 
                                customer_email, 
                                customer_address, 
                                customer_city, 
                                customer_zip, 
                                cust_notification_approval,
                                SMS_freq_preference,
                                cust_guid_device_id_notification, 
                                SMS_last_notification,
                                max(purchase_date),
                                count(purchase_id),
                                role 
                            from customers
                            left join lplp lp
                            on customer_uid = pur_customer_uid
                            group by customer_uid;  
                            """

                #print(query)
                items = execute(query, 'get', conn)
                print("3")
                print(items["code"])
                if items['code']==280:
                    items['message'] = 'Loaded successful'
                    items['result'] = items['result']
                    items['code'] = 200
                    return items
                else:
                    items['message'] = "Customer UID doesn't exists"
                    items['result'] = items['result']
                    items['code'] = 404
                    return items

            except:
                raise BadRequest('Request failed, please try again later.')
            finally:
                disconnect(conn)









class Meal_Detail(Resource):

    def get(self, date):
        response = {}
        items = {}
        print("date: ", date)
        try:
            conn = connect()
            print("1")
            query = """
                    select * 
                    from meals 
                    inner join menu
                        on meal_uid = menu_meal_id
                    where menu_date = \'""" + date + """\';
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Meals Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Date doesn't exists"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)










# class Meal_Detail(Resource):
#     def get(self):
#         response={}
#         items={}
#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             print("1")
#             date = data['date']
#             query = """
#                     select * 
#                     from meals 
#                     inner join menu
#                         on meal_uid = menu_meal_id
#                     where menu_meal_id = \'""" + date + """\';
#                     """
#             print(query)
#             items = execute(query, 'get', conn)
#             #print("SUBSTRING("SQL Tutorial", 5, 3")
#             print("2")
#             print(items)
#             if items['code'] == 280:
#                 items['message'] = 'Get Meal_detail successfully'
#                 print(items)
#                 #items['result'] = items['result']
#                 #print(items['code'])
#                 items['code'] = 200
#                 return items
#             else:
#                 items['message'] = 'Check sql query'
#                 items['code'] = 400
#                 return items
#         except:
#             print("3")
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)





class List_of_Meals(Resource):

    def get(self, date):
        response = {}
        items = {}
        print("date: ", date)
        try:
            conn = connect()
            print("1")
            query = """
                    select meal_name
                    from menu 
                    inner join meals
                        on meal_uid = menu_meal_id
                    where menu_date= \'""" + date + """\';
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Meals Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Date doesn't exists"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class Create_Group(Resource):

    def post(self):
        items={}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("1")
            group = data["group"]
            uid = data["id"]
            print("2")
            query = """
                    update customers
                    set notification_group = \'""" + group + """\'
                    where customer_uid = \'""" + uid + """\';
                    """
            print(query)
            items = execute(query, 'post', conn)
            if items['code'] == 281:
                items['message'] = 'Group updated successfully'
                print(items['code'])
                items['code'] = 200
                #return items
            else:
                items['message'] = 'Check sql query'
                items['code'] = 400
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


# class Latest_SMS(Resource):

#     def post(self):

#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             query = """
#                     update customers
#                     set SMS_last_notification = \'""" + data["message"] + """\'
#                     where customer_uid = \'""" + data["id"] + """\';
#                     """
#             print(query)
#             items = execute(query, 'post', conn)
#             if items['code'] == 281:
#                 items['message'] = 'Newest message updated successfully'
#                 print(items['code'])
#                 items['code'] = 200
#             else:
#                 items['message'] = 'Check sql query'
#                 items['code'] = 400
#             return items

#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)



# class Send_Notification(Resource):

#     def get(self):
#         items={}
#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             if data.get('group') is None or data.get('group') == "FALSE" or data.get('group') == False:
#                 group_sent = False
#             else:
#                 group_sent = True

#             if group_sent == True:
#                 query = """
#                 select * 
#                 from customers 
#                 where notification_group = \'""" + data["group"] + """\';
#                 """
#             else:
#                 query = """
#                 select * 
#                 from customers 
#                 where customer_uid = \'""" + data["id"] + """\';
#                 """
#             items = execute(query, 'get', conn)
#             if items['code']==280:
#                 items['message'] = 'Loaded successful'
#                 items['result'] = items['result']
#                 items['code'] = 200
#                 return items
#             else:
#                 items['message'] = "Customer UID doesn't exists"
#                 items['result'] = items['result']
#                 items['code'] = 404
#                 return items

#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)

#     def post(self):
#         items={}
#         try:
#             conn = connect()
#             data = request.get_json(force=True)
#             #message = data["message"]

#             query = """
#                     update customers
#                     set SMS_last_notification = \'""" + data["message"] + """\'
#                     where customer_uid = \'""" + data["id"] + """\';
#                     """
#             print(query)
#             items = execute(query, 'post', conn)
#             if items['code'] == 281:
#                 items['message'] = 'Newest message updated successfully'
#                 print(items['code'])
#                 items['code'] = 200
#             else:
#                 items['message'] = 'Check sql query'
#                 items['code'] = 400
#             return items

#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)


class Send_Twilio_SMS(Resource):

    def post(self):
        items = {}
        data = request.get_json(force=True)
        numbers = data['numbers']
        message = data['message']
        if not numbers:
            raise BadRequest('Request failed. Please provide the recipients field.')
        if not message:
            raise BadRequest('Request failed. Please provide the message field.')
        print('IN SMS----')
        print(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        for destination in numbers.split(','):
            client.messages.create(
                body = message,
                from_= '+19254815757',
                to = "+1" + destination
            )
        items['code'] = 200
        items['Message'] = 'SMS sent successfully to all recipients'
        return items




class get_recipes(Resource):

    def get(self, meal_id):
        response = {}
        items = {}
        print("meal_id: ", meal_id)
        try:
            conn = connect()
            print("1")
            query = """
                    select recipe_ingredient_id, recipe_ingredient_qty, recipe_measure_id
                    from recipes
                    where recipe_meal_id=\'""" + meal_id + """\';
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Recipe Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Date doesn't exists"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

#working here- needs update 
class update_recipe(Resource):

    def post(self):
        items={}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("1")
            qty = data["qty"]
            id = data["id"]
            #quantity=float(qty)-0
            measure = data["measure"]
            meal_id = data["meal_id"]
            recipe_uid = data["recipe_uid"]
            
            print("2")
            query = """
                    update recipes
                    set recipe_ingredient_id = \'""" + id + """\', 
                        recipe_ingredient_qty = \'""" + qty + """\', 
                        recipe_measure_id = \'""" + measure + """\'
                    where recipe_meal_id = \'""" + meal_id + """\'
                        and recipe_uid = \'""" + recipe_uid + """\';
                    """
            print(query)
            items = execute(query, 'post', conn)
            if items['code'] == 281:
                items['message'] = 'recipe updated successfully'
                print(items['code'])
                items['code'] = 200
                #return items
            else:
                items['message'] = 'Check sql query'
                items['code'] = 400
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

#meal_uid = get_new_id("CALL new_meal_uid", "get_new_meal_ID", conn)



class add_new_ingredient_recipe(Resource):

    def post(self):
        items={}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("1")
            qty = data["qty"]
            id = data["id"]
            measure = data["measure"]
            meal_id = data["meal_id"]
            #recipe_uid = get_new_id("CALL new_recipe_uid", "get_new_recipe_uid", conn)

            query1 = "CALL M4ME.new_recipe_uid"
            recipe_uid_query = execute(query1, 'get', conn)
            recipe_uid = recipe_uid_query['result'][0]['new_id']
            print(recipe_uid)
            query = """
                    INSERT INTO recipes (
                        recipe_uid, 
                        recipe_ingredient_id, 
                        recipe_ingredient_qty, 
                        recipe_measure_id,
                        recipe_meal_id
                        ) 
                        VALUES (
                        \'""" + recipe_uid + """\',
                        \'""" + id + """\',
                        \'""" + qty + """\',
                        \'""" + measure + """\',
                        \'""" + meal_id + """\'
                        );
                    """
            #print(query)
            items = execute(query, 'post', conn)
            print(items)
            if items['code'] == 281:
                items['message'] = 'recipe updated successfully'
                print(items['code'])
                items['code'] = 200
                #return items
            else:
                items['message'] = 'Check sql query'
                items['code'] = 400
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class create_recipe(Resource):

    def post(self):
        items={}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("1")
            qty = data["qty"]
            id = data["id"]
            measure = data["measure"]
            meal_id = data["meal_id"]
            print("2")
            query = """
                    INSERT INTO recipes (
                        recipe_meal_id, 
                        recipe_ingredient_id, 
                        recipe_ingredient_qty, 
                        recipe_measure_id
                        ) 
                        VALUES (
                        \'""" + meal_id + """\',
                        \'""" + id + """\',
                        \'""" + qty + """\',
                        \'""" + measure + """\'
                        );
                    """
            #print(query)
            items = execute(query, 'post', conn)
            print(items)
            if items['code'] == 281:
                items['message'] = 'recipe updated successfully'
                print(items['code'])
                items['code'] = 200
                #return items
            else:
                items['message'] = 'Check sql query'
                items['code'] = 400
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




#pur_business_uid
class get_orders(Resource):

    def get(self):
        response = {}
        items = {}
        #print("meal_id: ", meal_id)
        try:
            conn = connect()
            print("1")
            query = """
                    SELECT 
                        lplpibr_customer_uid,
                        customer_first_name,
                        customer_last_name,
                        customer_phone_num, 
                        customer_email, 
                        customer_address, 
                        customer_city, 
                        customer_zip,
                        lplpibr_items,
                        lplpibr_jt_item_uid,
                        lplpibr_jt_business_uid,
                        lplpibr_jt_item_name,
                        lplpibr_jt_qty,
                        lplpibr_jt_price
                    from customers
                    inner join M4ME.lplp_items_by_row
                    on customer_uid = lplpibr_customer_uid
                    where lplpibr_jt_business_uid = "200-000002";
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Orders Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Fail to load"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



#pur_business_uid
class get_supplys_by_date(Resource):

    def get(self):
        response = {}
        items = {}
        #print("meal_id: ", meal_id)
        try:
            conn = connect()
            print("1")
            query = """
                    SELECT 
                        #lplpibr_items,
                        lplpibr_jt_business_uid,
                        lplpibr_jt_item_uid,
                        lplpibr_jt_item_name,
                        lplpibr_jt_qty,
                        lplpibr_jt_id,
                        lplpibr_jt_price,
                        start_delivery_date,
                        purchase_date,
                        customer_uid
                        #SUM(lplpibr_jt_qty * lplpibr_jt_price) AS total
                        #count(
                    from M4ME.lplp_items_by_row
                    inner join purchases
                        on purchase_uid = lplpibr_purchase_uid
                    inner join customers
                        on customer_uid = lplpibr_customer_uid
                    where lplpibr_jt_business_uid is not null
                    order by lplpibr_jt_business_uid, lplpibr_jt_item_uid;
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Supply Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Fail to load"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


#pur_business_uid
class get_item_revenue(Resource):

    def get(self):
        response = {}
        items = {}
        #print("meal_id: ", meal_id)
        try:
            conn = connect()
            print("1")
            query = """
                    SELECT 
                        #lplpibr_items,
                        lplpibr_jt_business_uid,
                        lplpibr_jt_item_uid,
                        lplpibr_jt_item_name,
                        SUM(lplpibr_jt_qty) as qty, 
                        lplpibr_jt_id,
                        round(lplpibr_jt_price,2) as price,
                        #start_delivery_date,
                        #purchase_date,
                        SUM(lplpibr_jt_qty)*round(lplpibr_jt_price,2) AS total
                        #count(
                    from M4ME.lplp_items_by_row
                    inner join purchases
                        on purchase_uid = lplpibr_purchase_uid
                    where lplpibr_jt_business_uid is not null
                    group by lplpibr_jt_business_uid, lplpibr_jt_item_uid
                    order by lplpibr_jt_business_uid, lplpibr_jt_item_uid;
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Item Revenue Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Fail to load"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



#pur_business_uid
class get_total_revenue(Resource):

    def get(self):
        response = {}
        items = {}
        #print("meal_id: ", meal_id)
        try:
            conn = connect()
            print("1")
            query = """
                    SELECT lplpibr_jt_business_uid, round(SUM(tcalc.sumCol),2) as total
                    FROM (
                        SELECT
                            lplpibr_jt_business_uid, (SUM(lplpibr_jt_qty)*lplpibr_jt_price) AS sumCol
                        FROM M4ME.lplp_items_by_row
                        INNER JOIN
                            purchases
                            on purchase_uid = lplpibr_purchase_uid
                        where lplpibr_jt_business_uid is not null
                        group by lplpibr_jt_business_uid, lplpibr_jt_item_uid
                    ) as tcalc
                    GROUP BY lplpibr_jt_business_uid;
                    """
            items = execute(query, 'get', conn)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Total Revenue Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return response, 200
            else:
                items['message'] = "Fail to load"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class get_delivery_info(Resource):

    def get(self, purchase_id):
        response = {}
        items = {}
        print("purchase_id: ", purchase_id)
        try:
            conn = connect()
            print("1")
            query = """
                    select order_instructions, delivery_instructions, 
                            delivery_first_name,
                            delivery_last_name, delivery_phone_num,
                            delivery_email, delivery_address,
                            delivery_unit, delivery_city,
                            delivery_state, delivery_zip,
                            delivery_latitude, delivery_longitude
                    from lplp
                    where purchase_uid=\'""" + purchase_id + """\';
                    """
            items = execute(query, 'get', conn)
            print(items)
            print(items["code"])
            if items['code']==280:
                response['message'] = 'Info Loaded successful'
                response['result'] = items
                #response['code'] = 200
                print("2")
                return items, 200
            else:
                items['message'] = "Date doesn't exists"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



# class update_guid_notification(Resource):

#     def post(self, role):
#         response = {}
#         items = {}

#         try:
#             conn = connect()
#             data = request.get_json(force=True)

#             print(data)
#             if role == 'customer':
#                 uid = data['uid']
#                 guid = data['guid']
#                 notification = data['notification']
#                 query = """
#                         SELECT *
#                         FROM M4ME.customers c
#                         WHERE customer_uid = \'""" + uid + """\'
#                         """
#                 items = execute(query, 'get', conn)
#                 del data['uid']
#                 test = str(data).replace("'", "\"")
#                 print('test---------', test)
#                 data = "'" + test + "'"

#                 print(data)
#                 if items['result']:

#                     query = " " \
#                             "UPDATE M4ME.customers " \
#                             "SET cust_guid_device_id_notification  = (SELECT JSON_MERGE_PRESERVE(cust_guid_device_id_notification," + data + ")) " \
#                             "WHERE customer_uid = '" + str(uid) + "';" \
#                             ""

#                     items = execute(query, 'post', conn)
#                     print(items)
#                     if items['code'] == 281:
#                         items['code'] = 200
#                         items['message'] = 'Device_id notification and GUID updated'
#                     else:
#                         items['message'] = 'check sql query'

#                 else:
#                     items['message'] = "UID doesn't exists"

#                 return items

#             elif role == 'business':
#                 uid = data['uid']
#                 guid = data['guid']
#                 query = """
#                         SELECT *
#                         FROM M4ME.businesses b
#                         WHERE business_uid = \'""" + uid + """\'
#                         """
#                 items = execute(query, 'get', conn)

#                 del data['uid']
#                 test = str(data).replace("'", "\"")
#                 print('test---------', test)
#                 data = "'" + test + "'"

#                 if items['result']:
#                     data
#                     query = " " \
#                             "UPDATE M4ME.businesses " \
#                             "SET bus_guid_device_id_notification  = (SELECT JSON_MERGE_PRESERVE(bus_guid_device_id_notification," + data + ")) " \
#                             "WHERE business_uid = '" + str(uid) + "';" \
#                             ""

#                     items = execute(query, 'post', conn)

#                     if items['code'] == 281:
#                         items['code'] = 200
#                         items['message'] = 'Device_id notification and GUID updated'
#                     else:
#                         items['message'] = 'check sql query'

#                 else:
#                     items['message'] = "UID doesn't exists"

#                 return items

#             else:
#                 return 'choose correct option'

#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)


class update_guid_notification(Resource):

    def post(self, role, action):
        response = {}
        items = {}

        try:
            conn = connect()
            data = request.get_json(force=True)

            print(data)
            if role == 'customer' and action == 'add':
                uid = data['uid']
                guid = data['guid']
                notification = data['notification']
                query = """
                        SELECT *
                        FROM customers c
                        WHERE customer_uid = \'""" + uid + """\'
                        """
                items = execute(query, 'get', conn)
                del data['uid']
                test = str(data).replace("'", "\"")
                print('test---------', test)
                data = "'" + test + "'"

                print(data)
                if items['result']:

                    query = " " \
                            "UPDATE customers " \
                            "SET cust_guid_device_id_notification  = (SELECT JSON_MERGE_PRESERVE(cust_guid_device_id_notification," + data + ")) " \
                            "WHERE customer_uid = '" + str(uid) + "';" \
                            ""

                    items = execute(query, 'post', conn)
                    print(items)
                    if items['code'] == 281:
                        items['code'] = 200
                        items['message'] = 'Device_id notification and GUID updated'
                    else:
                        items['message'] = 'check sql query'

                else:
                    items['message'] = "UID doesn't exists"

                return items

            elif role == 'business' and action == 'add':
                uid = data['uid']
                guid = data['guid']
                query = """
                        SELECT *
                        FROM businesses b
                        WHERE business_uid = \'""" + uid + """\'
                        """
                items = execute(query, 'get', conn)

                del data['uid']
                test = str(data).replace("'", "\"")
                print('test---------', test)
                data = "'" + test + "'"

                if items['result']:
                    data
                    query = " " \
                            "UPDATE businesses " \
                            "SET bus_guid_device_id_notification  = (SELECT JSON_MERGE_PRESERVE(bus_guid_device_id_notification," + data + ")) " \
                            "WHERE business_uid = '" + str(uid) + "';" \
                            ""

                    items = execute(query, 'post', conn)

                    if items['code'] == 281:
                        items['code'] = 200
                        items['message'] = 'Device_id notification and GUID updated'
                    else:
                        items['message'] = 'check sql query'

                else:
                    items['message'] = "UID doesn't exists"

                return items

            #GUIDS

            elif role == 'customer' and action == 'update':
                query = """
                    SELECT cust_guid_device_id_notification
                    FROM customers c
                    WHERE customer_uid = \'""" + data['uid'] + """\';
                    """
                items = execute(query, 'get', conn)
                json_guid = json.loads(items['result'][0]['cust_guid_device_id_notification'])
                print('0', json_guid)
                for i, vals in enumerate(json_guid):
                    print(i, vals)
                    if vals == None or vals == 'null':
                        continue
                    if vals['guid'] == data['guid']:
                        print(vals)
                        json_guid[i]['notification'] = data['notification']
                        break
                if json_guid[0] == None:
                    print('none')
                    json_guid[0] = 'null'

                print('1', json_guid)
                guid = str(json_guid)
                guid = guid.replace("'", '"')
                print('2', guid)
                print(guid)
                guid = "[null," + guid[8:]
                print('replace',guid)
                query = """
                        UPDATE customers  
                        SET
                        cust_guid_device_id_notification = \'""" + guid + """\'
                        WHERE ( customer_uid  = '""" + data['uid'] + """' );
                        """
                print(query)
                items = execute(query, 'post', conn)
                if items['code'] != 281:
                    items['message'] = 'guid not updated check sql query and data'

                else:
                    print(items)
                    items['message'] = 'guid updated'
                return items

            elif role == 'business' and action == 'update':
                query = """
                    SELECT bus_guid_device_id_notification
                    FROM businesses b
                    WHERE business_uid = \'""" + data['uid'] + """\';
                    """
                items = execute(query, 'get', conn)
                json_guid = json.loads(items['result'][0]['bus_guid_device_id_notification'])
                for i, vals in enumerate(json_guid):
                    print(i, vals)
                    if vals == None or vals == 'null':
                        continue
                    if vals['guid'] == data['guid']:
                        print(vals)
                        json_guid[i]['notification'] = data['notification']
                        break
                if json_guid[0] == None:
                    json_guid[0] = 'null'

                guid = str(json_guid)
                guid = guid.replace("'", '"')
                print(guid)
                guid = "[null," + guid[8:]
                query = """
                        UPDATE  businesses
                        SET
                        bus_guid_device_id_notification = \'""" + guid + """\'
                        WHERE ( business_uid  = '""" + data['uid'] + """' );
                        """
                items = execute(query, 'post', conn)
                if items['code'] != 281:
                    items['message'] = 'guid not updated check sql query and data'

                else:
                    items['message'] = 'guid updated'
                return items

            else:
                return 'choose correct option'

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



# class Categorical_Options(Resource): #NEED TO FIX
#     def get(self, long, lat):
#         response = {}
#         items = {}

#         try:
#             conn = connect()

#             # query for businesses serving in customer's zone
#             query = """
#                     SELECT DISTINCT z_business_uid
#                     FROM
#                     (SELECT *,  
#                     IF (
#                     IF ((z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long) <= 0,
#                     \'""" + lat + """\' >=  (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long) * \'""" + long + """\' + z.LT_lat - z.LT_long * (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long),
#                     \'""" + lat + """\' <=   (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long) * \'""" + long + """\' + z.LT_lat - z.LT_long * (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long)) AND
                           
#                     \'""" + lat + """\' <= (z.RT_lat - z.LT_lat)/(z.RT_long - z.LT_long) * \'""" + long + """\' + z.RT_lat - z.RT_long * (z.RT_lat - z.LT_lat)/(z.RT_long - z.LT_long) AND
                           
#                     IF ((z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long) >= 0,  
#                     \'""" + lat + """\' >= (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long) * \'""" + long + """\' + z.RB_lat - z.RB_long * (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long),
#                     \'""" + lat + """\' <= (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long) * \'""" + long + """\' + z.RB_lat - z.RB_long * (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long)) AND
                           
#                     \'""" + lat + """\' >= (z.LB_lat - z.RB_lat)/(z.LB_long - z.RB_long) * \'""" + long + """\' + z.LB_lat - z.LB_long * (z.LB_lat - z.RB_lat)/(z.LB_long - z.RB_long), "TRUE", "FALSE") AS "In_Zone",
                     
#                     FORMAT((z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long),3) AS "LEFT_SLOPE",
#                     FORMAT((z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long),3) AS "RIGHT_SLOPE"
#                     FROM M4ME.zones z) AS DD
#                     WHERE In_Zone = 'True'
#                     ;
#                     """
#             items = execute(query, 'get', conn)

#             if items['code'] != 280:
#                 items['message'] = 'check sql query'
#                 return items

#             ids = []
#             for vals in items['result']:
#                 ids.append(vals['z_business_uid'])
#             print(ids)

#             #query for getting categorical data
#             query = """
#                     SELECT * 
#                     FROM M4ME.businesses as bus,
#                     (SELECT itm_business_uid, GROUP_CONCAT(DISTINCT item_type SEPARATOR ',') AS item_type
#                     FROM M4ME.items
#                     GROUP BY itm_business_uid) as itm
#                     WHERE bus.business_uid = itm.itm_business_uid AND bus.business_uid IN """ + str(tuple(ids)) + """;
#                     """
#             items = execute(query, 'get', conn)

#             if items['code'] != 280:
#                 items['message'] = 'check sql query'
#                 return items

#             items['message'] = 'Categorical options successful'
#             items['code'] = 200
#             return items
#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)




class getItems(Resource): #NED TO FIX
    def post(self):
        response = {}
        items = {}

        try:
            conn = connect()

            #OLD QUERY
            '''
            query = """
                    SELECT business_delivery_hours,business_uid
                    FROM M4ME.businesses;
                    """
            items = execute(query, 'get', conn)
            uids = []
            for vals in items['result']:
                open_days = json.loads(vals['business_delivery_hours'])
                print(open_days[day][1])
                if open_days[day][1] == '00:00:00':
                    continue
                uids.append(vals['business_uid'])
            query = """
                    SELECT it.*, bs.business_delivery_hours
                    FROM M4ME.items AS it, M4ME.businesses AS bs
                    WHERE it.itm_business_uid = bs.business_uid
                    AND bs.business_uid IN """ + str(tuple(uids)) + """;
                    """
            print(query)
            items = execute(query, 'get', conn)
            items['message'] = 'Items sent successfully'
            items['code'] = 200
            return items
            '''
            data = request.get_json(force=True)
            ids = data['ids']
            type = data['type']
            type.append('Random')
            type.append('Random2')
            ids.append('Random')
            ids.append('Random2')

            query = """
                    SELECT * 
                    FROM M4ME.items
                    WHERE item_type IN """ + str(tuple(type)) + """ AND itm_business_uid IN """ + str(tuple(ids)) + """;
                    """
            print(query)
            items = execute(query, 'get', conn)

            if items['code'] != 280:
                items['message'] = 'check sql query'
                return items

            items['message'] = 'Items sent successfully'
            items['code'] = 200
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class Refund(Resource): #add column called ref_payment_id
    # HTTP method POST

    def post(self):
        response = {}
        items = []
        try:
            #dtdt
            conn = connect()

            email = request.form.get('email')
            note = request.form.get('note')
            item_photo = request.files.get('item_photo')
            timeStamp = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
            payment= request.form.get('payment_id')
            query = ["CALL new_refund_uid;"]

            NewRefundIDresponse = execute(query[0], 'get', conn)
            NewRefundID = NewRefundIDresponse['result'][0]['new_id']
            print('INN')
            customer_phone = execute("""SELECT customer_phone_num FROM M4ME.customers WHERE customer_email = \'""" + email + "\';", 'get', conn)
            print('customer_phone---', customer_phone, '--dd')
            if not customer_phone['result']:

                items['result'] = email
                items['message'] = 'Email does not exists'
                items['code'] = 400

                return items

            ## add photo

            key = "REFUND" + "_" + NewRefundID
            print(key)
            item_photo_url = helper_upload_meal_img(item_photo, key)
            print(item_photo_url)

            phone = customer_phone['result'][0]['customer_phone_num']
            query_email = ["SELECT customer_email FROM M4ME.customers WHERE customer_email = \'" + email + "\';"]
            query_insert = [""" INSERT INTO M4ME.refunds
                            (
                                refund_uid,
                                created_at,
                                email_id,
                                phone_num,
                                image_url,
                                ref_payment_id
                                customer_note
                            )
                            VALUES
                            (
                            \'""" + NewRefundID + """\'
                            , \'""" + timeStamp + """\'
                            , \'""" + email + """\'
                            , \'""" + phone + """\'
                            , \'""" + item_photo_url + """\'
                            , \'""" + payment + """\'
                            , \'""" + note.replace("'", "") + """\');"""
                            ]

            emailExists = execute(query_email[0], 'get', conn)
            print('email_exists', emailExists)
            items = execute(query_insert[0], 'post', conn)
            print(items)
            if items['code'] != 281:
                items['message'] = 'check sql query and input'
                return items
            else:
                items['code'] = 200
                items['message'] = 'Refund info generated'
                return items

        except:
            print("Error happened while generating refund ticket")
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')





class business_details_update(Resource):
    def post(self, action):
            try:
                conn = connect()
                data = request.get_json(force=True)

                if action == 'Get':
                    query = "SELECT * FROM M4ME.businesses WHERE business_uid = \'" + data['business_uid'] + "\';"
                    item = execute(query, 'get', conn)
                    if item['code'] == 280:
                        if not item['result']:
                            item['message'] = 'No such business uid exists'
                        else:
                            item['message'] = 'Business table loaded successfully'
                        item['code'] = 200
                    else:
                        item['message'] = 'check sql query'
                        item['code'] = 490
                    return item
                else:
                    print("IN ELSE")
                    print(data)
                    print('IN')


                    business_association = str(data['business_association'])
                    business_association = "'" + business_association.replace("'", "\"") + "'"
                    business_hours = str(data['business_hours'])
                    business_hours = "'" + business_hours.replace("'", "\"") + "'"
                    business_accepting_hours = str(data['business_accepting_hours'])
                    business_accepting_hours = "'" + business_accepting_hours.replace("'", "\"") + "'"
                    business_delivery_hours = str(data['business_delivery_hours'])
                    business_delivery_hours = "'" + business_delivery_hours.replace("'", "\"") + "'"

                    query = """
                               UPDATE M4ME.businesses
                               SET 
                               business_created_at = \'""" + data["business_created_at"] + """\',
                               business_name = \'""" + data["business_name"] + """\',
                               business_type = \'""" + data["business_type"] + """\',
                               business_desc = \'""" + data["business_desc"] + """\',
                               business_association = """ + business_association + """,
                               business_contact_first_name = \'""" + data["business_contact_first_name"] + """\',
                               business_contact_last_name = \'""" + data["business_contact_last_name"] + """\',
                               business_phone_num = \'""" + data["business_phone_num"] + """\',
                               business_phone_num2 = \'""" + data["business_phone_num2"] + """\',
                               business_email = \'""" + data["business_email"] + """\',
                               business_hours = """ + business_hours + """,
                               business_accepting_hours = """ + business_accepting_hours + """,
                               business_delivery_hours = """ + business_delivery_hours + """,
                               business_address = \'""" + data["business_address"] + """\',
                               business_unit = \'""" + data["business_unit"] + """\',
                               business_city = \'""" + data["business_city"] + """\',
                               business_state = \'""" + data["business_state"] + """\',
                               business_zip = \'""" + data["business_zip"] + """\',
                               business_longitude = \'""" + data["business_longitude"] + """\',
                               business_latitude = \'""" + data["business_latitude"] + """\',
                               business_EIN = \'""" + data["business_EIN"] + """\',
                               business_WAUBI = \'""" + data["business_WAUBI"] + """\',
                               business_license = \'""" + data["business_license"] + """\',
                               business_USDOT = \'""" + data["business_USDOT"] + """\',
                               bus_notification_approval = \'""" + data["bus_notification_approval"] + """\',
                               bus_notification_device_id = \'""" + data["bus_notification_device_id"] + """\',
                               can_cancel = \'""" + data["can_cancel"] + """\',
                               delivery = \'""" + data["delivery"] + """\',
                               reusable = \'""" + data["reusable"] + """\',
                               business_image = \'""" + data["business_image"] + """\',
                               business_password = \'""" + data["business_password"] + """\'
                               WHERE business_uid = \'""" + data["business_uid"] + """\' ;
                             """
                    print(query)
                    item = execute(query, 'post', conn)
                    print(item)
                    if item['code'] == 281:
                        item['code'] = 200
                        item['message'] = 'Business info updated'
                    else:
                        item['message'] = 'check sql query'
                        item['code'] = 490
                    return item

            except:
                print("Error happened while outputting from business table")
                raise BadRequest('Request failed, please try again later.')
            finally:
                disconnect(conn)
                print('process completed')




class orders_by_business(Resource): #need to fix

    def get(self):

        try:
            conn = connect()
            query = """
                    SELECT *,deconstruct.* 
                    FROM M4ME.purchases, 
                         JSON_TABLE(items, '$[*]' COLUMNS (
                                    qty VARCHAR(255)  PATH '$.qty',
                                    name VARCHAR(255)  PATH '$.name',
                                    price VARCHAR(255)  PATH '$.price',
                                    item_uid VARCHAR(255)  PATH '$.item_uid',
                                    itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                         ) AS deconstruct; 
                    """
            items = execute(query, 'get', conn)
            if items['code'] == 280:
                items['message'] = 'Orders by business view loaded successful'
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
            return items
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class order_actions(Resource):

    def post(self, action):

        try:
            conn = connect()
            data = request.get_json(force=True)
            purchase_uid = data['purchase_uid'] if data.get('purchase_uid') is not None else 'NULL'
            if action == 'Delete':
                print('IN DELETE')

                purchase_uid = data['purchase_uid'] if data.get('purchase_uid') is not None else 'NULL'

                if purchase_uid == 'NULL':
                    return 'UID Incorrect'

                query_pur = """
                        DELETE FROM M4ME.purchases WHERE (purchase_uid = \'""" + purchase_uid + """\');
                        """
                item = execute(query_pur, 'post', conn)
                if item['code'] == 281:
                    item['message'] = 'Order deleted'
                    item['code'] = 200
                else:
                    item['message'] = 'Check sql query'

                query_pay = """
                        DELETE FROM M4ME.payments WHERE (pay_purchase_uid = \'""" + purchase_uid + """\');
                        """
                item = execute(query_pay, 'post', conn)
                if item['code'] == 281:
                    item['message'] = 'order deleted successful'
                    item['code'] = 200
                else:
                    item['message'] = 'Check sql query'

            elif action == 'delivery_status_YES':
                print('DELIVERY_YES')

                query = """
                        UPDATE M4ME.purchases 
                        SET delivery_status = 'Yes' 
                        WHERE purchase_uid = \'""" + purchase_uid + """\';
                        """
                print(query)
                item = execute(query, 'post', conn)
                print(item)

                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'Delivery Status updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

            elif action == 'delivery_status_NO':

                print('DELIVERY_NO')
                query = """
                        UPDATE M4ME.purchases 
                        SET delivery_status = 'No' 
                        WHERE purchase_uid = \'""" + purchase_uid + """\';
                        """

                item = execute(query, 'post', conn)

                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'Delivery Status updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

            elif action == 'item_delete':
                print('item_delete')
                #itm = str(data['item_data'])
                itm = json.dumps(data['item_data'])
                print(itm)
                itm = "'[" + ", ".join([str(val).replace("'", "\"") if val else "NULL" for val in data['item_data']]) + "]'"

                query = """ 
                        UPDATE M4ME.purchases 
                        SET 
                        items = """  + itm + """
                        WHERE (purchase_uid = \'""" + purchase_uid + """\');
                        """
                print(query)
                item = execute(query, 'post', conn)
                print(item)

                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'items deleted updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

            else:
                return 'Select proper option'

            return item

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class admin_report(Resource):

    def get(self, uid):

        try:
            conn = connect()

            query = """
                    SELECT *,deconstruct.*, sum(price) as Amount  
                    FROM M4ME.purchases, 
                         JSON_TABLE(items, '$[*]' COLUMNS (
                                    qty VARCHAR(255)  PATH '$.qty',
                                    name VARCHAR(255)  PATH '$.name',
                                    price VARCHAR(255)  PATH '$.price',
                                    item_uid VARCHAR(255)  PATH '$.item_uid',
                                    itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                         ) AS deconstruct
                    WHERE itm_business_uid = \'""" + uid + """\'
                    GROUP BY purchase_uid;
                    """

            items = execute(query, 'get', conn)
            if items['code'] == 280:
                items['message'] = 'Report data successful'
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class customer_info(Resource):

    def get(self):

        try:
            conn = connect()
            query = """
                    SELECT  
                    cust.customer_uid,
                    cust.customer_first_name,
                    cust.customer_last_name,
                    cust.customer_email,
                    cust.customer_phone_num,
                    cust.customer_address,
                    cust.customer_unit,
                    cust.customer_city,
                    cust.customer_zip,
                    cust.customer_created_at,
                    cust.cust_notification_approval,
                    cust.SMS_freq_preference,
                    cust.cust_guid_device_id_notification,
                    cust.SMS_last_notification,
                    (SELECT business_name FROM M4ME.businesses AS bus WHERE bus.business_uid = deconstruct.itm_business_uid) AS business_name,
                    deconstruct.*, 
                    count(deconstruct.itm_business_uid) AS number_of_orders, 
                    max(pay.payment_time_stamp) AS latest_order_date
                                FROM M4ME.purchases , 
                                     JSON_TABLE(items, '$[*]' COLUMNS (
                                                qty VARCHAR(255)  PATH '$.qty',
                                                name VARCHAR(255)  PATH '$.name',
                                                price VARCHAR(255)  PATH '$.price',
                                                item_uid VARCHAR(255)  PATH '$.item_uid',
                                                itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                                     ) AS deconstruct, M4ME.payments AS pay, M4ME.customers AS cust
                    WHERE purchase_uid = pay.pay_purchase_uid AND pur_customer_uid = cust.customer_uid
                            and items like "%200-000002%"
                    GROUP BY deconstruct.itm_business_uid, pur_customer_uid
                    ; 
                    """
            items = execute(query, 'get', conn)

            if items['code'] == 280:

                items['message'] = 'Customer info Loaded successful'
                items['code'] = 200
                return items
            else:
                items['message'] = "check sql query"
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



# class Send_Notification(Resource):

#     def post(self, role):

#         def deconstruct(uids, role):
#             print('IN decon')
#             conn = connect()
#             uids_array = uids.split(',')
#             output = []
#             for uid in uids_array:
#                 if role == 'customer':
#                     query = """SELECT cust_guid_device_id_notification FROM customers WHERE customer_uid = \'""" + uid + """\';"""
#                     items = execute(query, 'get', conn)

#                     if items['code'] != 280:
#                         items['message'] = "check sql query"
#                         items['code'] = 404
#                         return items

#                     json_val = items['result'][0]['cust_guid_device_id_notification']

#                 else:

#                     query = """SELECT bus_guid_device_id_notification FROM businesses WHERE business_uid = \'""" + uid + """\';"""
#                     items = execute(query, 'get', conn)

#                     if items['code'] != 280:
#                         items['message'] = "check sql query"
#                         items['code'] = 404
#                         return items

#                     json_val = items['result'][0]['bus_guid_device_id_notification']

#                 if json_val != 'null':
#                     print("in deconstruct")
#                     print(type(json_val))
#                     print(json_val)
#                     input_val = json.loads(json_val)
#                     print(type(input_val))
#                     print(input_val)
#                     for vals in input_val:
#                         print('vals--', vals)
#                         print(type(vals))
#                         if vals == None:
#                             continue
#                         print('guid--', vals['guid'])
#                         print('notification---', vals['notification'])
#                         if vals['notification'] == 'TRUE':
#                             output.append('guid_' + vals['guid'])
#             output = ",".join(output)
#             print('output-----', output)
#             return output
#         print('IN---')

#         hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)


#         print('role----', role)
#         uids = request.form.get('uids')
#         message = request.form.get('message')
#         print('uids', uids)
#         print('role', role)
#         tags = deconstruct(uids, role)
#         print('tags-----', tags)

#         if tags == []:
#             return 'No GUIDs found for the UIDs provided'
#         #tags = uids
#         if tags is None:
#             raise BadRequest('Request failed. Please provide the tag field.')
#         if message is None:
#             raise BadRequest('Request failed. Please provide the message field.')
#         tags = tags.split(',')
#         tags = list(set(tags))
#         print('tags11-----', tags)
#         print('RESULT-----',tags)
#         for tag in tags:
#             print('tag-----', tag)
#             print(type(tag))
#             alert_payload = {
#                 "aps" : {
#                     "alert" : message,
#                 },
#             }
#             hub.send_apple_notification(alert_payload, tags = tag)

#             fcm_payload = {
#                 "data":{"message": message}
#             }
#             hub.send_gcm_notification(fcm_payload, tags = tag)

#         return 200



class Send_Notification(Resource):

    def post(self, role):

        def deconstruct(uids, role):
            print('IN decon')
            conn = connect()
            uids_array = uids.split(',')
            output = []
            for uid in uids_array:
                if role == 'customer':
                    query = """SELECT cust_guid_device_id_notification FROM sf.customers WHERE customer_uid = \'""" + uid + """\';"""
                    items = execute(query, 'get', conn)

                    if items['code'] != 280:
                        items['message'] = "check sql query"
                        items['code'] = 404
                        return items

                    json_val = items['result'][0]['cust_guid_device_id_notification']

                else:

                    query = """SELECT bus_guid_device_id_notification FROM sf.businesses WHERE business_uid = \'""" + uid + """\';"""
                    items = execute(query, 'get', conn)

                    if items['code'] != 280:
                        items['message'] = "check sql query"
                        items['code'] = 404
                        return items

                    json_val = items['result'][0]['bus_guid_device_id_notification']

                if json_val != 'null':
                    print("in deconstruct")
                    print(type(json_val))
                    print(json_val)
                    input_val = json.loads(json_val)
                    print(type(input_val))
                    print(input_val)
                    for vals in input_val:
                        print('vals--', vals)
                        print(type(vals))
                        if vals == None:
                            continue
                        print('guid--', vals['guid'])
                        print('notification---', vals['notification'])
                        if vals['notification'] == 'TRUE':
                            output.append('guid_' + vals['guid'])
            output = ",".join(output)
            print('output-----', output)
            return output
        print('IN---')

        hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)


        print('role----', role)
        uids = request.form.get('uids')
        message = request.form.get('message')
        print('uids', uids)
        print('role', role)
        tags = deconstruct(uids, role)
        print('tags-----', tags)

        if tags == []:
            return 'No GUIDs found for the UIDs provided'
        #tags = uids
        if tags is None:
            raise BadRequest('Request failed. Please provide the tag field.')
        if message is None:
            raise BadRequest('Request failed. Please provide the message field.')
        tags = tags.split(',')
        tags = list(set(tags))
        print('tags11-----', tags)
        print('RESULT-----',tags)
        for tag in tags:
            print('tag-----', tag)
            print(type(tag))
            alert_payload = {
                "aps" : {
                    "alert" : message,
                },
            }
            hub.send_apple_notification(alert_payload, tags = tag)

            fcm_payload = {
                "data":{"message": message}
            }
            hub.send_gcm_notification(fcm_payload, tags = tag)

        return 200






class Get_Registrations_From_Tag(Resource):
    def get(self, tag):
        hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)
        if tag is None:
            raise BadRequest('Request failed. Please provide the tag field.')
        response = hub.get_all_registrations_with_a_tag(tag)
        response = str(response.read())
        print(response)
        return response,200

class Create_or_Update_Registration_iOS(Resource):
    def post(self):
        hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)
        registration_id = request.form.get('registration_id')
        device_token = request.form.get('device_token')
        tags = request.form.get('tags')

        if tags is None:
            raise BadRequest('Request failed. Please provide the tags field.')
        if registration_id is None:
            raise BadRequest('Request failed. Please provide the registration_id field.')
        if device_token is None:
            raise BadRequest('Request failed. Please provide the device_token field.')

        response = hub.create_or_update_registration_iOS(registration_id, device_token, tags)

        return response.status

class Update_Registration_With_GUID_iOS(Resource):
    def post(self):
        hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)
        guid = request.form.get('guid')
        tags = request.form.get('tags')
        if guid is None:
            raise BadRequest('Request failed. Please provide the guid field.')
        if tags is None:
            raise BadRequest('Request failed. Please provide the tags field.')
        response = hub.get_all_registrations_with_a_tag(guid)
        xml_response = str(response.read())[2:-1]
        # root = ET.fromstring(xml_response)
        xml_response_soup = BeautifulSoup(xml_response,features="html.parser")
        appleregistrationdescription = xml_response_soup.feed.entry.content.appleregistrationdescription
        registration_id = appleregistrationdescription.registrationid.get_text()
        device_token = appleregistrationdescription.devicetoken.get_text()
        old_tags = appleregistrationdescription.tags.get_text().split(",")
        tags = tags.split(",")
        new_tags = set(old_tags + tags)
        new_tags = ','.join(new_tags)
        print(f"tags: {old_tags}\ndevice_token: {device_token}\nregistration_id: {registration_id}")

        if device_token is None or registration_id is None:
            raise BadRequest('Something went wrong in retriving device_token and registration_id')

        response = hub.create_or_update_registration_iOS(registration_id, device_token, new_tags)
        # for type_tag in root.findall('feed/entry/content/AppleRegistrationDescription'):
        #     value = type_tag.get('Tags')
        #     print(value)
        # print("\n\n--- RESPONSE ---")
        # print(str(response.status) + " " + response.reason)
        # print(response.msg)
        # print(response.read())
        # print("--- END RESPONSE ---")
        return response.status

class Update_Registration_With_GUID_Android(Resource):
    def post(self):
        hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)
        guid = request.form.get('guid')
        tags = request.form.get('tags')
        if guid is None:
            raise BadRequest('Request failed. Please provide the guid field.')
        if tags is None:
            raise BadRequest('Request failed. Please provide the tags field.')
        response = hub.get_all_registrations_with_a_tag(guid)
        xml_response = str(response.read())[2:-1]
        # root = ET.fromstring(xml_response)
        xml_response_soup = BeautifulSoup(xml_response,features="html.parser")
        gcmregistrationdescription = xml_response_soup.feed.entry.content.gcmregistrationdescription
        registration_id = gcmregistrationdescription.registrationid.get_text()
        gcm_registration_id = gcmregistrationdescription.gcmregistrationid.get_text()
        old_tags = gcmregistrationdescription.tags.get_text().split(",")
        tags = tags.split(",")
        new_tags = set(old_tags + tags)
        new_tags = ','.join(new_tags)
        print(f"tags: {old_tags}\nregistration_id: {registration_id}\ngcm_registration_id: {gcm_registration_id}")

        if gcm_registration_id is None or registration_id is None:
            raise BadRequest('Something went wrong in retriving gcm_registration_id and registration_id')

        response = hub.create_or_update_registration_android(registration_id, gcm_registration_id, new_tags)
        return response.status

class Get_Tags_With_GUID_iOS(Resource):
    def get(self, tag):
        hub = NotificationHub(NOTIFICATION_HUB_KEY, NOTIFICATION_HUB_NAME, isDebug)
        guid = tag
        if guid is None:
            raise BadRequest('Request failed. Please provide the guid field.')
        response = hub.get_all_registrations_with_a_tag(guid)
        print(response)
        xml_response = str(response.read())[2:-1]
        # root = ET.fromstring(xml_response)
        xml_response_soup = BeautifulSoup(xml_response,features="html.parser")
        appleregistrationdescription = xml_response_soup.feed.entry.content.appleregistrationdescription
        registration_id = appleregistrationdescription.registrationid.get_text()
        device_token = appleregistrationdescription.devicetoken.get_text()
        old_tags = appleregistrationdescription.tags.get_text().split(",")
        return old_tags



class history(Resource):
    # Fetches ALL DETAILS FOR A SPECIFIC USER

    def get(self, email):
        response = {}
        items = {}
        print("user_email: ", email)
        try:
            conn = connect()
            query = """
                    SELECT * 
                    FROM M4ME.purchases as pur, M4ME.payments as pay
                    WHERE pur.purchase_uid = pay.pay_purchase_uid AND pur.delivery_email = \'""" + email + """\'
                    ORDER BY pur.purchase_date DESC; 
                    """
            items = execute(query, 'get', conn)

            items['message'] = 'History Loaded successful'
            items['code'] = 200
            return items
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


#uses pur_business_uid 
class purchase_Data_SF(Resource):
    def post(self):
            response = {}
            items = {}
            try:
                conn = connect()
                data = request.get_json(force=True)

                # Purchases start here

                query = "CALL M4ME.new_purchase_uid"
                newPurchaseUID_query = execute(query, 'get', conn)
                newPurchaseUID = newPurchaseUID_query['result'][0]['new_id']

                purchase_uid = newPurchaseUID
                purchase_date = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
                purchase_id = purchase_uid
                purchase_status = 'ACTIVE'
                pur_customer_uid = data['pur_customer_uid']
                #pur_business_uid = data['pur_business_uid']
                #items_pur = data['items']
                items_pur = "'[" + ", ".join([str(val).replace("'", "\"") if val else "NULL" for val in data['items']]) + "]'"

                order_instructions = data['order_instructions']
                delivery_instructions = data['delivery_instructions']
                order_type = data['order_type']
                delivery_first_name = data['delivery_first_name']
                delivery_last_name = data['delivery_last_name']
                delivery_phone_num = data['delivery_phone_num']
                delivery_email = data['delivery_email']
                delivery_address = data['delivery_address']
                delivery_unit = data['delivery_unit']
                delivery_city = data['delivery_city']
                delivery_state = data['delivery_state']
                delivery_zip = data['delivery_zip']
                delivery_latitude = data['delivery_latitude']
                delivery_longitude = data['delivery_longitude']
                purchase_notes = data['purchase_notes']

                query = "SELECT * FROM M4ME.customers " \
                        "WHERE customer_email =\'"+delivery_email+"\';"

                items = execute(query, 'get', conn)

                print('ITEMS--------------', items)

                if not items['result']:
                    items['code'] = 404
                    items['message'] = "User email doesn't exists"
                    return items

                print('in insert-------')

                query_insert = """ 
                                    INSERT INTO M4ME.purchases
                                    SET
                                    purchase_uid = \'""" + newPurchaseUID + """\',
                                    purchase_date = \'""" + purchase_date + """\',
                                    purchase_id = \'""" + purchase_id + """\',
                                    purchase_status = \'""" + purchase_status + """\',
                                    pur_customer_uid = \'""" + pur_customer_uid + """\',
                                    items = """ + items_pur + """,
                                    order_instructions = \'""" + order_instructions + """\',
                                    delivery_instructions = \'""" + delivery_instructions + """\',
                                    order_type = \'""" + order_type + """\',
                                    delivery_first_name = \'""" + delivery_first_name + """\',
                                    delivery_last_name = \'""" + delivery_last_name + """\',
                                    delivery_phone_num = \'""" + delivery_phone_num + """\',
                                    delivery_email = \'""" + delivery_email + """\',
                                    delivery_address = \'""" + delivery_address + """\',
                                    delivery_unit = \'""" + delivery_unit + """\',
                                    delivery_city = \'""" + delivery_city + """\',
                                    delivery_state = \'""" + delivery_state + """\',
                                    delivery_zip = \'""" + delivery_zip + """\',
                                    delivery_latitude = \'""" + delivery_latitude + """\',
                                    delivery_longitude = \'""" + delivery_longitude + """\',
                                    purchase_notes = \'""" + purchase_notes + """\';
                                """
                items = execute(query_insert, 'post', conn)

                print('execute')
                if items['code'] == 281:
                    items['code'] = 200
                    items['message'] = 'Purchase info updated'

                else:
                    items['message'] = 'check sql query'
                    items['code'] = 490


                # Payments start here


                query = "CALL M4ME.new_payment_uid"
                newPaymentUID_query = execute(query, 'get', conn)
                newPaymentUID = newPaymentUID_query['result'][0]['new_id']

                payment_uid = newPaymentUID
                payment_id = payment_uid
                pay_purchase_uid = newPurchaseUID
                pay_purchase_id = newPurchaseUID
                payment_time_stamp = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
                start_delivery_date = data['start_delivery_date']
                pay_coupon_id = data['pay_coupon_id']
                amount_due = data['amount_due']
                amount_discount = data['amount_discount']
                amount_paid = data['amount_paid']
                info_is_Addon = data['info_is_Addon']
                cc_num = data['cc_num']
                cc_exp_date = data['cc_exp_date']
                cc_cvv = data['cc_cvv']
                cc_zip = data['cc_zip']
                charge_id = data['charge_id']
                payment_type = data['payment_type']

                query_insert = [""" 
                                    INSERT INTO  M4ME.payments
                                    SET
                                    payment_uid = \'""" + payment_uid + """\',
                                    payment_id = \'""" + payment_id + """\',
                                    pay_purchase_uid = \'""" + pay_purchase_uid + """\',
                                    pay_purchase_id = \'""" + pay_purchase_id + """\',
                                    payment_time_stamp = \'""" + payment_time_stamp + """\',
                                    start_delivery_date = \'""" + start_delivery_date + """\',
                                    pay_coupon_id = \'""" + pay_coupon_id + """\',
                                    amount_due = \'""" + amount_due + """\',
                                    amount_discount = \'""" + amount_discount + """\',
                                    amount_paid = \'""" + amount_paid + """\',
                                    info_is_Addon = \'""" + info_is_Addon + """\',
                                    cc_num = \'""" + cc_num + """\',
                                    cc_exp_date = \'""" + cc_exp_date + """\',
                                    cc_cvv = \'""" + cc_cvv + """\',
                                    cc_zip = \'""" + cc_zip + """\',
                                    charge_id = \'""" + charge_id + """\',
                                    payment_type = \'""" + payment_type + """\';
                                    
                                """]

                print(query_insert)
                item = execute(query_insert[0], 'post', conn)

                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'Payment info updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

                return item

            except:
                print("Error happened while inserting in purchase table")

                raise BadRequest('Request failed, please try again later.')
            finally:
                disconnect(conn)



class update_all_items(Resource):

    def post(self, uid):

        try:
            conn = connect()
            query = """
                    UPDATE M4ME.items
                    SET item_status = 'Active'
                    WHERE itm_business_uid = \'""" + uid + """\';
                    """
            items = execute(query, 'post', conn)
            if items['code'] == 281:
                items['message'] = 'items status updated successfully'
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class all_businesses(Resource):

    def get(self):
        try:
            conn = connect()

            query = """
                    SELECT business_uid, business_name FROM M4ME.businesses; 
                    """
            items = execute(query, 'get', conn)
            if items['code'] == 280:
                items['message'] = 'Business data returned successfully'
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class addItems(Resource):
    def post(self, action):

        items = {}
        try:
            conn = connect()

            if action == 'Insert':
                itm_business_uid = request.form.get('itm_business_uid')
                item_name = request.form.get('item_name')
                item_status = request.form.get('item_status')
                item_type = request.form.get('item_type')
                item_desc = request.form.get('item_desc')
                item_unit = request.form.get('item_unit')
                item_price = request.form.get('item_price')
                item_sizes = request.form.get('item_sizes')
                favorite = request.form.get('favorite')
                item_photo = request.files.get('item_photo')
                exp_date = request.form.get('exp_date')
                print('IN')

                query = ["CALL M4ME.new_items_uid;"]
                NewIDresponse = execute(query[0], 'get', conn)
                NewID = NewIDresponse['result'][0]['new_id']
                key =  "items/" + NewID
                print(key)
                print(request.form)
                print(request.files)
                item_photo_url = helper_upload_meal_img(item_photo, key)
                print(item_photo_url)
                print("NewRefundID = ", NewID)
                TimeStamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print("TimeStamp = ", TimeStamp)

                # INSERT query
                query_insert =  '''
                                INSERT INTO M4ME.items
                                SET 
                                itm_business_uid = \'''' + itm_business_uid + '''\',
                                item_name = \'''' + item_name + '''\',
                                item_status = \'''' + item_status + '''\',
                                item_type = \'''' + item_type + '''\',
                                item_desc = \'''' + item_desc + '''\',
                                item_unit = \'''' + item_unit + '''\',
                                item_price = \'''' + item_price + '''\',
                                item_sizes = \'''' + item_sizes + '''\',
                                favorite = \'''' + favorite + '''\',
                                item_photo = \'''' + item_photo_url + '''\',
                                exp_date = \'''' + exp_date + '''\',
                                created_at = \'''' + TimeStamp + '''\',
                                item_uid = \'''' + NewID + '''\';
                                '''
                items = execute(query_insert, 'post', conn)
                print(items)

                if items['code'] == 281:
                    items['message'] = 'Item added successfully'
                    items['code'] = 200
                else:
                    items['message'] = 'check sql query'
                    items['code'] = 490
                return items

            elif action == 'Update':
                # Update query

                item_uid = request.form.get('item_uid')
                itm_business_uid = request.form.get('itm_business_uid')
                item_name = request.form.get('item_name')
                item_status = request.form.get('item_status')
                item_type = request.form.get('item_type')
                item_desc = request.form.get('item_desc')
                item_unit = request.form.get('item_unit')
                item_price = request.form.get('item_price')
                item_sizes = request.form.get('item_sizes')
                favorite = request.form.get('favorite')
                print('In')
                item_photo = request.files.get('item_photo') if request.files.get('item_photo') is not None else 'NULL'
                print('oout')
                exp_date = request.form.get('exp_date')
                key = str(item_uid)

                if item_photo == 'NULL':
                    print('IFFFFF------')

                    query_update =  '''
                                    UPDATE M4ME.items
                                    SET 
                                    itm_business_uid = \'''' + itm_business_uid + '''\',
                                    item_name = \'''' + item_name + '''\',
                                    item_status = \'''' + item_status + '''\',
                                    item_type = \'''' + item_type + '''\',
                                    item_desc = \'''' + item_desc + '''\',
                                    item_unit = \'''' + item_unit + '''\',
                                    item_price = \'''' + item_price + '''\',
                                    item_sizes = \'''' + item_sizes + '''\',
                                    favorite = \'''' + favorite + '''\',
                                    exp_date = \'''' + exp_date + '''\'
                                    WHERE item_uid = \'''' + item_uid + '''\';
                                '''
                else:
                    print('ELSE--------')
                    item_photo_url = helper_upload_meal_img(item_photo, key)
                    query_update =  '''
                                    UPDATE M4ME.items
                                    SET 
                                    itm_business_uid = \'''' + itm_business_uid + '''\',
                                    item_name = \'''' + item_name + '''\',
                                    item_status = \'''' + item_status + '''\',
                                    item_type = \'''' + item_type + '''\',
                                    item_desc = \'''' + item_desc + '''\',
                                    item_unit = \'''' + item_unit + '''\',
                                    item_price = \'''' + item_price + '''\',
                                    item_sizes = \'''' + item_sizes + '''\',
                                    favorite = \'''' + favorite + '''\',
                                    item_photo = \'''' + item_photo_url + '''\',
                                    exp_date = \'''' + exp_date + '''\'
                                    WHERE item_uid = \'''' + item_uid + '''\';
                                '''

                items = execute(query_update, 'post', conn)
                print(items)

                if items['code'] == 281:
                    items['message'] = 'Item updated successfully'
                    items['code'] = 200
                else:
                    items['message'] = 'check sql query'
                    items['code'] = 490
                return items

            else:

                # Update item_status
                print('ELSE-------------')
                item_uid = request.form.get('item_uid')
                item_status = request.form.get('item_status')
                query_status =  '''
                                UPDATE M4ME.items
                                SET 
                                item_status = \'''' + item_status + '''\'
                                WHERE item_uid = \'''' + item_uid + '''\';
                                '''
                items = execute(query_status, 'post', conn)
                print(items)

                if items['code'] == 281:
                    items['message'] = 'Item updated successfully'
                    items['code'] = 200
                else:
                    items['message'] = 'check sql query'
                    items['code'] = 490
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class pid_history(Resource):
    # Fetches ALL DETAILS FOR A SPECIFIC USER

    def get(self, pid):
        response = {}
        items = {}
        print("purchase_id: ", pid)
        try:
            conn = connect()
            query = """
                    SELECT * 
                    FROM M4ME.purchases as pur, M4ME.payments as pay
                    WHERE pur.purchase_uid = pay.pay_purchase_uid AND pur.purchase_id = \'""" + pid + """\'
                    ORDER BY pur.purchase_date DESC; 
                    """
            items = execute(query, 'get', conn)

            items['message'] = 'History Loaded successful'
            items['code'] = 200
            return items
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class UpdatePassword(Resource):
    def post(self):
            response = {}
            item = {}
            try:
                conn = connect()
                data = request.get_json(force=True)

                #query = "CALL M4ME.new_profile"
                #new_profile_query = execute(query, 'get', conn)
                #new_profile = newPaymentUID_query['result'][0]['new_id']
                print("1")
                uid= data['uid']
                #old_password=data['passworld']
                salt = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
                #print("1.5")
                new_password = sha512((data['password'] + salt).encode()).hexdigest()
                print('password------', new_password)
                algorithm = "SHA512"
                #new_password = sha512((data['password'] + salt).encode()).hexdigest()
                customer_insert_query = [""" 
                                    update M4ME.customers
                                    set
                                    password_hashed = \'""" + new_password + """\'
                                    WHERE customer_uid =\'""" + uid + """\';  
                                """]
                print("2")
                print(customer_insert_query)
                item = execute(customer_insert_query[0], 'post', conn)
                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'Password info updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

                return item

            except:
                print("Error happened while inserting in customer table")
                raise BadRequest('Request failed, please try again later.')
            finally:
                disconnect(conn)
                print('process completed')





class Change_Purchase_ID (Resource):
    def refund_calculator(self, info_res,  conn):

        # Getting the original start and end date for requesting purchase
        start_delivery_date = datetime.strptime(info_res['start_delivery_date'], "%Y-%m-%d %H-%M-%S")
        # check for SKIP. Let consider the simple case. The customer can change their purchases if and only if their purchase
        # still active.
        week_remaining = int(info_res['payment_frequency'])
        print("remaining")
        print(week_remaining)
        end_delivery_date = start_delivery_date + timedelta(days=(week_remaining) * 7)
        skip_query = """
                    SELECT COUNT(delivery_day) AS skip_count FROM 
                        (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM meals_selected
                            WHERE sel_purchase_id = '""" + info_res['purchase_id'] + """'
                            GROUP BY sel_menu_date) AS GB 
                            INNER JOIN meals_selected S
                            ON S.sel_purchase_id = GB.sel_purchase_id
                                AND S.sel_menu_date = GB.sel_menu_date
                                AND S.selection_time = GB.max_selection_time
                    WHERE S.sel_menu_date >= '""" + start_delivery_date.strftime("%Y-%m-%d %H-%M-%S") + """'
                        AND S.sel_menu_date <= '""" + datetime.now().strftime("%Y-%m-%d %H-%M-%S") + """'
                        AND delivery_day = 'SKIP'
                    ORDER BY S.sel_menu_date;
                    """
        skip_res = simple_get_execute(skip_query, "SKIP QUERY", conn)
        if skip_res[1] != 200:
            return skip_res
        skip = int(skip_res[0].get('skip_count')) if skip_res[0].get('skip_count') else 0
        if datetime.now().date() > start_delivery_date.date():
            delivered = (datetime.now().date() - start_delivery_date.date()).days//7 + 1 - skip
            week_remaining -= delivered
        elif (datetime.now().date() > end_delivery_date.date()):
            print("There is something wrong with the query to get info for the requested purchase.")
            response = {'message': "Internal Server Error."}
            return response, 500
        item_price = json.loads(info_res['items'])[0].get('price')
        customer_paid = float(item_price)
        # get the price of the new item.
        items_query = """
                        SELECT * FROM subscription_items
                        WHERE item_name = '""" + info_res['item_name'] + """'
                        """
        items_res = simple_get_execute(items_query, "GET Subscription_items QUERY", conn)
        if items_res[1] != 200:
            return items_res
        price = {}
        for item in items_res[0]['result']:
            price[item['num_issues']] = item['item_price']
        refund = 0
        if info_res['num_issues'] == 4: # 4 week prepaid
            print("matching 4 week pre-pay")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid - float(price[2]) - float(price[1])
            elif week_remaining == 2:
                refund = customer_paid - float(price[2])
            elif week_remaining == 3:
                refund = customer_paid - float(price[2])
            elif week_remaining == 4:
                refund = customer_paid
        elif info_res['num_issues'] == 2:
            print("matching 2 week Pre-pay")
            print("r0")
            print(week_remaining)
            if week_remaining == 0:
                refund = 0
                print("r1")
            elif week_remaining == 1:
                print("r2")
                print(customer_paid)
                print(price[1])
                refund = customer_paid - float(price[1])
                
            elif week_remaining == 2:
                refund = customer_paid
                print("r3")
        elif info_res['num_issues'] == 1:
            print("matching weekly")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid
        return {"week_remaining": week_remaining, "refund_amount": refund}

    def stripe_refund (self, refund_info, conn):
        refund_amount = refund_info['refund_amount']
        # retrieve charge info from stripe to determine how much refund amount left on current charge_id
        # if refund amount left on current charge_id < refund amount needed then trace back the latest previous payment
        # to get the next stripe_charge_id
        if refund_info.get('stripe_charge_id'):
            stripe_retrieve_info = stripe.Charge.retrieve(refund_info['stripe_charge_id'])
            return "OK"
        else:
            return None

    def post(self):
        try:
            conn = connect()
            response = {}
            # For this update_purchase endpoint, we should consider to ask customer provide their identity to make sure the right
            # person is doing what he/she want.
            # Also, using POST to protect sensitive information.
            data = request.get_json(force=True)
            #customer_email = data['customer_email']
            #print("0")
            password = data.get('password')
            refresh_token = data.get('refresh_token')
            #print("0.5")
            cc_num = str(data['cc_num'])
            cc_exp_date = data['cc_exp_year'] + data['cc_exp_month'] + "01"
            #print("0.7")
            cc_cvv = data['cc_cvv']
            cc_zip = data['cc_zip']
            purchaseID = data['purchase_id']
            new_item_id = data['new_item_id']
            customer_uid = data["customer_id"]
            #print("0.9")
            items = "'[" + ", ".join([str(item).replace("'", "\"") if item else "NULL" for item in data['items']]) + "]'"
            #print(items)
            print("1")

            #Check user's identity
            cus_query = """
                        SELECT password_hashed,
                                mobile_refresh_token
                        FROM customers
                        WHERE customer_uid = '""" + customer_uid + """';
                        """
            cus_res = simple_get_execute(cus_query, "Update_Purchase - Check Login", conn)
            print("1.5")
            print(cus_res)
            if cus_res[1] != 200:
                print("1.6")
                return cus_res
            if not password and not refresh_token:
                print("1.7")
                raise BadRequest("Request failed, please try again later.")
            elif password:
                print("1.8")
                if password != cus_res[0]['result'][0]['password_hashed']:
                    response['message'] = 'Wrong password'
                    return response, 401
            elif refresh_token:
                print("1.9")
                print(refresh_token)
                if refresh_token != cus_res[0]['result'][0]['mobile_refresh_token']:
                    print("1.95")
                    response['message'] = 'Token Invalid'
                    return response, 401
            # query info for requesting purchase
            # Get info of requesting purchase_id
            print("2")
            info_query = """
                        SELECT pur.*, pay.*, sub.*
                        FROM purchases pur, payments pay, subscription_items sub
                        WHERE pur.purchase_uid = pay.pay_purchase_uid
                            AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
                                                    FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
                            AND pur.purchase_uid = '""" + purchaseID + """'
                            AND pur.purchase_status='ACTIVE';  
                        """
            info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
            print(info_res)
            if info_res[1] != 200:
                print(info_res[1])
                return {"message": "Internal Server Error"}, 500
            # Calculate refund
            #print("2.5")
            print(info_res[0])
            refund_info = self.refund_calculator(info_res[0]['result'][0], conn)
            print("refund_info : ", refund_info)
            refund_amount = refund_info['refund_amount']
            #print("3")
            # price for the new purchase
            # this query below for querying the price may be redundant, the front end can send it in data['items']
            # Should we do it here to make sure that the front end did not make any error?
            item_query = """
                        SELECT * FROM subscription_items 
                        WHERE item_uid = '""" + new_item_id + """';
                        """
            item_res = simple_get_execute(item_query, "QUERY PRICE FOR NEW PURCHASE.", conn)
            if item_res[1] != 200:
                return {"message": "Internal Server Error"}, 500
            amount_will_charge = float(item_res[0]['result'][0]['item_price']) - refund_amount
            # Process stripe
            print("1: ", amount_will_charge)
            if amount_will_charge > 0:
                #charge with stripe
                #need code for charging here
                pass
            elif amount_will_charge < 0:
                print('refund_info: ', refund_info)
                # establishing more info for refund_info before we feed it in stripe_refund
                # refund_info['refund_amount'] = 0 - amount_will_charge
                # refund_info['stripe_charge_id'] = info_res[0]['result'][0]['charge_id']
                self.stripe_refund(refund_info, conn)
                # refund
            print("amount_will_charge: ", amount_will_charge)
            #gathering data before writting info to database
            # need to calculate the start_delivery_date
            start_delivery_date = "2020-11-30 00-00-00"
            info_res = info_res[0]['result'][0]

            payment_id = info_res.get("payment_id")
            purchase_id = info_res.get("purchase_id")
            customer_uid = info_res.get("pur_customer_uid")
            delivery_first_name = info_res.get("delivery_first_name")
            delivery_last_name = info_res.get("delivery_last_name")
            delivery_email = info_res.get("delivery_email")
            delivery_phone = info_res.get("delivery_phone_num")
            delivery_address = info_res.get("delivery_address")
            delivery_unit = info_res.get("delivery_unit")
            delivery_city = info_res.get("delivery_city")
            delivery_state = info_res.get("delivery_state")
            delivery_zip = info_res.get("delivery_zip")
            delivery_instructions = info_res.get("delivery_instructions") if info_res.get('delivery_instruction') else "NULL"
            delivery_longitude = info_res.get("delivery_longitude")
            delivery_latitude = info_res.get("delivery_latitude")
            order_instructions = info_res.get("order_instructions") if info_res.get("order_instructions") else "NULL"
            purchase_notes = info_res.get("purchase_notes") if info_res.get("purchase_notes") else "NULL"
            # get the new ids

            purchase_uid = get_new_purchaseID(conn)
            if purchase_uid[1] == 500:
                print(purchaseId[0])
                return {"message": "Internal Server Error."}, 500
            payment_uid = get_new_paymentID(conn)
            if payment_uid[1] == 500:
                print(payment_uid[0])
                return {"message": "Internal Server Error."}, 500
            # write the new purchase_id and payment_id into database
                # write into Payments table
            queries = [
                '''
                INSERT INTO M4ME.payments
                SET payment_uid = "''' + payment_uid + '''",
                                        payment_time_stamp = "''' + getNow() + '''",
                                        start_delivery_date = "''' + start_delivery_date + '''",
                                        payment_id = "''' + payment_id + '''",
                                        pay_purchase_id = "''' + purchase_id + '''",
                                        pay_purchase_uid = "''' + purchase_uid + '''",
                                        amount_due = "''' + str(round(amount_will_charge,2)) + '''",
                                        amount_discount = 0,
                                        amount_paid = "''' + str(round(amount_will_charge,2)) + '''",
                                        pay_coupon_id = NULL,
                                        charge_id = NULL,
                                        payment_type = NULL,
                                        info_is_Addon = "FALSE",
                                        cc_num = "''' + str(cc_num) + '''", 
                                        cc_exp_date = "''' + str(cc_exp_date) + '''", 
                                        cc_cvv = "''' + str(cc_cvv) + '''", 
                                        cc_zip = "''' + str(cc_zip) + '''";
                ''',
                '''
                INSERT INTO  M4ME.purchases
                SET purchase_uid = "''' + purchase_uid + '''",
                                        purchase_date = "''' + getNow() + '''",
                                        purchase_id = "''' + purchase_id + '''",
                                        purchase_status = 'ACTIVE',
                                        pur_customer_uid = "''' + customer_uid + '''",
                                        delivery_first_name = "''' + delivery_first_name + '''",
                                        delivery_last_name = "''' + delivery_last_name + '''",
                                        delivery_email = "''' + delivery_email + '''",
                                        delivery_phone_num = "''' + str(delivery_phone) + '''",
                                        delivery_address = "''' + delivery_address + '''",
                                        delivery_unit = "''' + str(delivery_unit) + '''",
                                        delivery_city = "''' + delivery_city + '''",
                                        delivery_state = "''' + delivery_state + '''",
                                        delivery_zip = "''' + str(delivery_zip) + '''",
                                        delivery_instructions = "''' + delivery_instructions + '''",
                                        delivery_longitude = "''' + delivery_longitude + '''",
                                        delivery_latitude = "''' + delivery_latitude + '''",
                                        items = ''' + items + ''',
                                        order_instructions = "''' + order_instructions + '''",
                                        purchase_notes = "''' + purchase_notes + '''";'''
            ]

            response = simple_post_execute(queries, ["PAYMENTS", "PURCHASES"], conn)

            if response[1] == 201:
                response[0]['payment_id'] = payment_uid
                response[0]['purchase_id'] = purchase_uid
                query = '''UPDATE M4ME.purchases SET purchase_status = "CANCELLED" WHERE purchase_uid = "''' + purchaseID + '";'
                simple_post_execute([query], ["UPDATE OLD PURCHASES"], conn)
                return response

            else:
                if "payment_uid" in locals() and "purchase_uid" in locals():
                    execute("""DELETE FROM payments WHERE payment_uid = '""" + payment_uid + """';""", 'post', conn)
                    execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchase_uid + """';""", 'post',
                            conn)
                return {"message": "Internal Server Error."}, 500

        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)



class Get_Upcoming_Menu_Date(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    # CUSTOMER QUERY 4A: UPCOMING MENUS
                    SELECT DISTINCT menu_date
                    FROM M4ME.menu
                    WHERE menu_date > CURDATE() AND
                    menu_date <= ADDDATE(CURDATE(), 43)
                    order by menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Menu selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class Update_Delivery_Info_Address (Resource):
    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            #print(data)
            [first_name, last_name, purchase_uid] = destructure(data, "first_name", "last_name", "purchase_uid")
            #print(first_name)
            [phone, email] = destructure(data, "phone", "email")
            [address, unit, city, state, zip] = destructure(data, 'address', 'unit', 'city', 'state', 'zip')
            #[cc_num, cc_cvv, cc_zip, cc_exp_date] = [str(value) if value else None for value in destructure(data, "cc_num", "cc_cvv", "cc_zip", "cc_exp_date")]
            #print("1")
            #should re-calculator the longtitude and latitude before update address
            
            queries = ['''UPDATE M4ME.purchases 
                            SET delivery_first_name= "''' + first_name + '''",
                                delivery_last_name = "''' + last_name + '''",
                                delivery_phone_num = "''' + phone + '''",
                                delivery_email = "''' + email + '''", 
                                delivery_address = "''' + address + '''",
                                delivery_unit = "''' + unit + '''",
                                delivery_city = "''' + city + '''",
                                delivery_state = "''' + state + '''",
                                delivery_zip = "''' + zip + '''"
                            WHERE purchase_uid = "''' + purchase_uid + '''";'''

                    ]
            #print("3")
            res = simple_post_execute(queries, ["UPDATE PURCHASE'S INFO"], conn)
            if res[1] == 201:
                return {"message": "Update Successful"}, 200
            else:
                print("Something Wrong with the Update queries")
                return {"message": "Update Failed"}, 500
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)






class report_order_customer_pivot_detail(Resource):

    def get(self, report, uid):

        try:
            conn = connect()
            if report == 'order':
                query = """
                        SELECT purchase_uid, purchase_date, delivery_first_name, delivery_last_name, delivery_phone_num, delivery_email, delivery_address, delivery_unit, delivery_city, delivery_state, delivery_zip, deconstruct.*, amount_paid, (SELECT business_name from M4ME.businesses WHERE business_uid = itm_business_uid) AS business_name
                        FROM M4ME.purchases, M4ME.payments,
                             JSON_TABLE(items, '$[*]' COLUMNS (
                                        qty VARCHAR(255)  PATH '$.qty',
                                        name VARCHAR(255)  PATH '$.name',
                                        price VARCHAR(255)  PATH '$.price',
                                        item_uid VARCHAR(255)  PATH '$.item_uid',
                                        itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                             ) AS deconstruct
                        WHERE purchase_uid = pay_purchase_uid AND purchase_status = 'ACTIVE' AND itm_business_uid = \'""" + uid + """\';
                        """

                items = execute(query, 'get', conn)

                if items['code'] != 280:
                    items['message'] = 'Check sql query'
                    return items
                else:

                    items['message'] = 'Report data successful'
                    items['code'] = 200
                    result = items['result']
                    dict = {}
                    for vals in result:
                        if vals['purchase_uid'] in dict:
                            dict[vals['purchase_uid']].append(vals)
                        else:
                            dict[vals['purchase_uid']] = [vals]

                    data = []

                    for key, vals in dict.items():

                        tmp = vals[0]
                        print('tmp----', tmp)
                        data.append([tmp['purchase_date'],
                                     tmp['delivery_first_name'],
                                     tmp['delivery_last_name'],
                                     tmp['delivery_phone_num'],
                                     tmp['delivery_email'],
                                     tmp['delivery_address'],
                                     tmp['delivery_unit'],
                                     tmp['delivery_city'],
                                     tmp['delivery_state'],
                                     tmp['delivery_zip'],
                                     tmp['amount_paid']
                                     ])
                        for items in vals:
                            data.append([items['name'],
                                        items['qty'],
                                        items['price']
                                        ])


                    si = io.StringIO()
                    cw = csv.writer(si)
                    cw.writerow(['Open Orders'])
                    for item in data:
                        cw.writerow(item)

                    orders = si.getvalue()
                    output = make_response(orders)
                    output.headers["Content-Disposition"] = "attachment; filename=order_details.csv"
                    output.headers["Content-type"] = "text/csv"
                    return output
            elif report == 'customer':
                query = """
                        SELECT pur_customer_uid, purchase_uid, purchase_date, delivery_first_name, delivery_last_name, delivery_phone_num, delivery_email, delivery_address, delivery_unit, delivery_city, delivery_state, delivery_zip, deconstruct.*, amount_paid, sum(price) as Amount
                        FROM M4ME.purchases, M4ME.payments,
                             JSON_TABLE(items, '$[*]' COLUMNS (
                                        qty VARCHAR(255)  PATH '$.qty',
                                        name VARCHAR(255)  PATH '$.name',
                                        price VARCHAR(255)  PATH '$.price',
                                        item_uid VARCHAR(255)  PATH '$.item_uid',
                                        itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                             ) AS deconstruct
                        WHERE purchase_uid = pay_purchase_uid AND purchase_status = 'ACTIVE' AND itm_business_uid = \'""" + uid + """\'
                        GROUP BY pur_customer_uid;
                        """

                items = execute(query, 'get', conn)

                if items['code'] != 280:
                    items['message'] = 'Check sql query'
                    return items
                else:

                    items['message'] = 'Report data successful'
                    items['code'] = 200
                    result = items['result']
                    print('result------', result)
                    data = []

                    for vals in result:

                        tmp = vals
                        print('tmp----', tmp)
                        data.append([tmp['delivery_first_name'],
                                     tmp['delivery_last_name'],
                                     tmp['delivery_phone_num'],
                                     tmp['delivery_email'],
                                     tmp['delivery_address'],
                                     tmp['delivery_unit'],
                                     tmp['delivery_city'],
                                     tmp['delivery_state'],
                                     tmp['delivery_zip'],
                                     tmp['Amount']
                                     ])



                    si = io.StringIO()
                    cw = csv.writer(si)
                    for item in data:
                        cw.writerow(item)

                    orders = si.getvalue()
                    output = make_response(orders)
                    output.headers["Content-Disposition"] = "attachment; filename=customer_details.csv"
                    output.headers["Content-type"] = "text/csv"
                    return output
            elif report == 'pivot':
                query = """
                        SELECT pur_customer_uid, purchase_uid, purchase_date, delivery_first_name, delivery_last_name, delivery_phone_num, delivery_email, delivery_address, delivery_unit, delivery_city, delivery_state, delivery_zip, deconstruct.*, amount_paid, (SELECT business_name from M4ME.businesses WHERE business_uid = itm_business_uid) AS business_name
                        FROM M4ME.purchases, M4ME.payments,
                             JSON_TABLE(items, '$[*]' COLUMNS (
                                        qty VARCHAR(255)  PATH '$.qty',
                                        name VARCHAR(255)  PATH '$.name',
                                        price VARCHAR(255)  PATH '$.price',
                                        item_uid VARCHAR(255)  PATH '$.item_uid',
                                        itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                             ) AS deconstruct
                        WHERE purchase_uid = pay_purchase_uid AND purchase_status = 'ACTIVE' AND itm_business_uid = \'""" + uid + """\';
                        """

                items = execute(query, 'get', conn)

                if items['code'] != 280:
                    items['message'] = 'Check sql query'
                    return items
                else:

                    items['message'] = 'Report data successful'
                    items['code'] = 200
                    result = items['result']
                    itm_dict = {}
                    for vals in result:
                        if vals['name'] in itm_dict:
                            itm_dict[vals['name']] += int(vals['qty'])
                        else:
                            itm_dict[vals['name']] = int(vals['qty'])
                    print('ddddddd------', itm_dict)
                    dict = {}
                    for vals in result:
                        if vals['pur_customer_uid'] in dict:
                            dict[vals['pur_customer_uid']].append(vals)
                        else:
                            dict[vals['pur_customer_uid']] = [vals]

                    print('dict----', dict)
                    si = io.StringIO()
                    cw = csv.DictWriter(si, ['Name', 'Email', 'Phone', 'Total'] + list(itm_dict.keys()))
                    cw.writeheader()
                    glob_tot = 0
                    for key, vals in dict.items():
                        print('VALSSS---', vals)
                        items = {groc['name']:groc['qty'] for groc in vals}
                        total_sum = 0
                        for tp_key, tp_vals in items.items():
                            total_sum += int(tp_vals)
                        glob_tot += total_sum
                        print('items-----------------', items)
                        items['Name'] = vals[0]['delivery_first_name'] + vals[0]['delivery_last_name']
                        items['Email'] = vals[0]['delivery_email']
                        items['Phone'] = vals[0]['delivery_phone_num']
                        items['Total'] = total_sum
                        cw.writerow(items)

                    cw.writerow({'Name': 'Total', 'Total': glob_tot, **itm_dict})

                    orders = si.getvalue()
                    output = make_response(orders)
                    output.headers["Content-Disposition"] = "attachment; filename=pivot_table.csv"
                    output.headers["Content-type"] = "text/csv"
                    return output
            else:
                return "choose correct option"
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class Latest_activity(Resource):
    def get(self, user_id):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(
                """ select acc.*,pur.*,mp.meal_plan_desc,
                        pay.*
                        from ptyd_accounts acc
                        left join ptyd_payments pay
                        on acc.user_uid = pay.buyer_id
                        left join ptyd_purchases pur
                        on pay.purchase_id = pur.purchase_id
                        left join ptyd_meal_plans mp
                        on pur.meal_plan_id = mp.meal_plan_id
                        where acc.user_uid = \'""" + user_id + """\'
                        and pay.payment_time_stamp in
                        (select latest_time_stamp from
                            (SELECT buyer_id, purchase_id, MAX(payment_time_stamp) as "latest_time_stamp" FROM
                                (SELECT * FROM ptyd_payments where buyer_id = \'""" + user_id + """\') temp
                                group by buyer_id, purchase_id) temp1
                        )
                        order by pur.purchase_id
                        ;
                        """, 'get', conn)

            response['message'] = 'successful'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




#allows business to see who ordered what for each item
class Orders_by_Items(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    select d_menu_date,
                            jt_name,
                            group_concat(lplpibr_customer_uid),
                            group_concat(jt_qty)
                    FROM fcs_items_by_row
                    group by jt_name, d_menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class Orders_by_Purchase_Id(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    SELECT
                        d_menu_date,
                        d_purchase_id,
                        group_concat(jt_name),
                        group_concat(jt_qty)
                    FROM fcs_items_by_row
                    group by d_purchase_id, d_menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class AppleEmail(Resource):
    #  RETURNS EMAIL FOR APPLE LOGIN ID

    def post(self):

        try:
            conn = connect()
            data = request.get_json(force=True)
            social_id = data.get('social_id')

            query = """
                    SELECT customer_email
                    FROM M4ME.customers c
                    WHERE social_id = \'""" + social_id + """\'
                    """

            print(query)

            items = execute(query, 'get', conn)
            print("Items:", items)
            print(items['code'])
            print(items['result'])

            if items['code'] == 280:
                items['message'] = 'Email Returned'
                items['result'] = items['result']
                print(items['code'])
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
                items['result'] = items['result']
                items['code'] = 400
            return items

        except:
            raise BadRequest('AppleEmail Request failed, please try again later.')
        finally:
            disconnect(conn)




class Order_by_items_with_Date(Resource):
    def get(self, date):
        response = {}
        items = {}
        try:
            conn = connect()
            query = """
                    select d_menu_date,
                            jt_name,
                            group_concat(lplpibr_customer_uid),
                            group_concat(jt_qty)
                    FROM fcs_items_by_row
                    where d_menu_date = \'""" + date + """\'
                    group by jt_name, d_menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





#make a copy that takes input of purchase_id
class Orders_by_Purchase_Id_with_Date(Resource):
    def get(self, date):
        response = {}
        items = {}
        try:
            conn = connect()
            query = """
                    SELECT
                        d_menu_date,
                        d_purchase_id,
                        group_concat(jt_name),
                        group_concat(jt_qty)
                    FROM fcs_items_by_row
                    where d_menu_date = \'""" + date + """\' 
                    group by d_purchase_id, d_menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




# key_checkers are only for Mobile applications
class Stripe_Payment_key_checker(Resource):
    def post(self):
        response = {}
        data = request.get_json(force=True)
        # key_test = "pk_test_6RSoSd9tJgB2fN2hGkEDHCXp00MQdrK3Tw"
        # key_live = "pk_live_g0VCt4AW6k7tyjRw61O3ac5a00Tefdbp8E"

        key_test = stripe_public_test_key
        key_live = stripe_public_live_key

        if data['key'] == key_test:
            # if app is in testing
            stripe_status = "Test"
            # if app is live
            #stripe_status = "Live"
            return stripe_status

        elif data['key'] == key_live:
            # if app is in testing
            #stripe_status = "Test"
            # if app is live
            stripe_status = "Live"
            return stripe_status

        else:
            return 200
        return response


# key_checkers are only for Mobile applications
class Paypal_Payment_key_checker(Resource):
    def post(self):
        response = {}
        data = request.get_json(force=True)
        key_test = paypal_client_test_key
        key_live = paypal_client_live_key
        #print("Key:", key_test)
        if data['key'] == key_test:
            # if app is in testing
            paypal_status = 'Test'
            # if app is live
            #paypal_status = 'Live'
            print(paypal_status)
            return paypal_status

        elif data['key'] == key_live:
            # if app is in testing
            #paypal_status = 'Test'
            # if app is live
            paypal_status = 'Live'
            print(paypal_status)
            return paypal_status

        else:
            return 200
        return response



class Ingredients_Recipe_Specific (Resource):
    def get(self, recipe_uid):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 4: 
                    #  MEALS & MENUS  5. CREATE NEW INGREDIENT:
                    SELECT * FROM M4ME.ingredients
                    LEFT JOIN M4ME.inventory
                        ON ingredient_uid = inventory_ingredient_id
                    LEFT JOIN M4ME.conversion_units
                        ON inventory_measure_id = measure_unit_uid
                    inner join recipes
                        on recipe_ingredient_id=ingredient_uid
                    where recipe_meal_id= \'""" + recipe_uid + """\' ;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)


class Edit_Meal_Plan (Resource):
    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            item_uid= data['item_uid']
            item_name= data['item_name']
            item_desc= data['item_desc']
            item_price= data['item_price']
            item_sizes= data['item_sizes']
            num_items= data['num_items']
            item_photo= data['item_photo']
            #deliveries_per_week= data['menu_uid']
            info_headline= data['info_headline']
            info_footer= data['info_footer']
            info_weekly_price= data['info_weekly_price']
            payment_frequency= data['payment_frequency']
            shipping= data['shipping']

            #print(data["delivery_days"])
            #print([str(item) for item in data['delivery_days']])
            #print(type(data["delivery_days"]))
            #temp=  data["delivery_days"].split(",")
            #delivery_days = data["delivery_days"]#''.join([letter for item in temp if letter.isalnum()])#data["delivery_days"].split(',')
            #print(delivery_days)
            #meal_price = str(data['meal_price'])
            query = """
                    UPDATE subscription_items
                    SET item_name = '""" + item_name + """',
                        item_desc = '""" + item_desc + """',
                        item_price = '""" + item_price + """',
                        item_sizes = '""" + item_sizes + """',
                        num_items = '""" + num_items + """',
                        item_photo = '""" + item_photo + """',
                        info_headline = '""" + info_headline + """',
                        info_footer = '""" + info_footer + """',
                        info_weekly_price = '""" + info_weekly_price + """',
                        payment_frequency = '""" + payment_frequency + """',
                        shipping = '""" + shipping + """'
                    where item_uid = '""" + item_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            print(response[1])
            if response[1] != 201:
                return response
            response[0]['item_uid'] = item_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class get_Fee_Tax(Resource):
    def get(self, z_id, day):
        try:
            conn = connect()
            
            query = """
                    SELECT service_fee, tax_rate, delivery_fee, z_delivery_time AS delivery_time
                    FROM M4ME.zones
                    WHERE zone_uid = \'""" + z_id + """\' AND z_delivery_day = \'""" + day + """\';
                    """
            items = execute(query, 'get', conn)
            print("1")
            print(items)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting taxes")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')


class Update_Fee_Tax (Resource):
    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            service_fee= data['service_fee']
            tax_rate= data['tax_rate']
            delivery_fee= data['delivery_fee']
            zone= data['zone']
            query = """
                    Update zones
                    set
                        service_fee = \'""" + service_fee + """\',
                        tax_rate = \'""" + tax_rate + """\',
                        delivery_fee = \'""" + delivery_fee + """\'
                    WHERE zone = \'""" + zone + """\';
                    """
            items = execute(query, 'post', conn)
            if items['code'] != 281:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting taxes")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')


class get_Zones (Resource):
    def get(self):
        try:
            conn = connect()
            
            query = """
                    SELECT *
                    FROM M4ME.zones;
                    """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting zones")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')



class Update_Zone (Resource):
    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("0")
            zone_uid= data['zone_uid']
            z_business_uid= data['z_business_uid']
            area= data['area']
            zone= data['zone']
            zone_name= data['zone_name']
            print("0.5")
            z_businesses= data['z_businesses']
            z_delivery_day= data['z_delivery_day']
            z_delivery_time= data['z_delivery_time']
            z_accepting_day= data['z_accepting_day']
            z_accepting_time= data['z_accepting_time']
            service_fee= data['service_fee']
            tax_rate= data['tax_rate']
            delivery_fee= data['delivery_fee']
            LB_long= data['LB_long']
            LB_lat= data['LB_lat']
            LT_long= data['LT_long']
            LT_lat= data['LT_lat']
            RT_long= data['RT_long']
            RT_lat= data['RT_lat']
            RB_long= data['RB_long']
            RB_lat= data['RB_lat']
            
            print("1")
            query = """
                    update zones
                    set
                        z_business_uid= '""" + z_business_uid + """',
                        area= '""" + area + """',
                        zone= '""" + zone + """',
                        zone_name= '""" + zone_name + """',
                        z_businesses= '""" + z_businesses + """',
                        z_delivery_day= '""" + z_delivery_day + """',
                        z_delivery_time= '""" + z_delivery_time + """',
                        z_accepting_day= '""" + z_accepting_day + """',
                        z_accepting_time= '""" + z_accepting_time + """',
                        service_fee = \'""" + service_fee + """\',
                        tax_rate = \'""" + tax_rate + """\',
                        delivery_fee = \'""" + delivery_fee + """\',
                        LB_long = \'""" + LB_long + """\',
                        LB_lat = \'""" + LB_lat + """\',
                        LT_long = \'""" + LT_long + """\',
                        LT_lat = \'""" + LT_lat + """\',
                        RT_long = \'""" + RT_long + """\',
                        RT_lat = \'""" + RT_lat + """\',
                        RB_long = \'""" + RB_long + """\',
                        RB_lat = \'""" + RB_lat + """\'
                    where zone_uid= '""" + zone_uid + """';
                    """
            items = execute(query, 'post', conn)
            print(items)
            if items['code'] != 281:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while updating zones")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')


class update_zones(Resource):

    def post(self, action):

        try:
            conn = connect()
            data = request.get_json(force=True)

            if action == 'create':

                get_uid = "CALL M4ME.new_zone_uid();"
                items = execute(get_uid, 'get', conn)
                if items['code'] != 280:
                    items['message'] = 'check sql query for getting zone uid'
                    return items
                print(items)
                uid = items['result'][0]['new_id']
                print(uid)
                z_businesses = str(data['z_businesses'])
                z_businesses = "'" + z_businesses.replace("'", "\"") + "'"
                query = """
                        INSERT INTO M4ME.zones 
                        (zone_uid, z_business_uid, area, zone, zone_name, z_businesses, z_delivery_day, z_delivery_time, z_accepting_day, z_accepting_time, service_fee, delivery_fee, tax_rate, LB_long, LB_lat, LT_long, LT_lat, RT_long, RT_lat, RB_long, RB_lat)
                         VALUES(
                         \'""" + uid + """\',
                          \'""" + data['z_business_uid'] + """\',
                          \'""" + data['area'] + """\',
                           \'""" + data['zone'] + """\',
                            \'""" + data['zone_name'] + """\',
                            """ + z_businesses + """,
                            \'""" + data['z_delivery_day'] + """\',
                            \'""" + data['z_delivery_time'] + """\',
                            \'""" + data['z_accepting_day'] + """\',
                            \'""" + data['z_accepting_time'] + """\',
                            \'""" + data['service_fee'] + """\',
                            \'""" + data['delivery_fee'] + """\',
                            \'""" + data['tax_rate'] + """\',
                            \'""" + data['LB_long'] + """\',
                            \'""" + data['LB_lat'] + """\',
                            \'""" + data['LT_long'] + """\',
                            \'""" + data['LT_lat'] + """\',
                            \'""" + data['RT_long'] + """\',
                            \'""" + data['RT_lat'] + """\',
                            \'""" + data['RB_long'] + """\',
                            \'""" + data['RB_lat'] + """\')
                        """
                #print('QUERY--', query)
                items = execute(query, 'post', conn)
                if items['code'] != 281:
                    items['message'] = 'check sql query for creating zones'
                return items

            elif action == 'update':
                z_businesses = str(data['z_businesses'])
                z_businesses = "'" + z_businesses.replace("'", "\"") + "'"
                query = """
                        UPDATE M4ME.zones
                        SET
                        z_business_uid = \'""" + data['z_business_uid'] + """\',
                        area = \'""" + data['area'] + """\',
                        zone = \'""" + data['zone'] + """\',
                        zone_name = \'""" + data['zone_name'] + """\',
                        z_businesses = """ + z_businesses + """,
                        z_delivery_day = \'""" + data['z_delivery_day'] + """\',
                        z_delivery_time = \'""" + data['z_delivery_time'] + """\',
                        z_accepting_day = \'""" + data['z_accepting_day'] + """\',
                        z_accepting_time = \'""" + data['z_accepting_time'] + """\',
                        service_fee = \'""" + data['service_fee'] + """\',
                        delivery_fee = \'""" + data['delivery_fee'] + """\',
                        tax_rate = \'""" + data['tax_rate'] + """\',
                        LB_long = \'""" + data['LB_long'] + """\',
                        LB_lat = \'""" + data['LB_lat'] + """\',
                        LT_long = \'""" + data['LT_long'] + """\',
                        LT_lat = \'""" + data['LT_lat'] + """\',
                        RT_long = \'""" + data['RT_long'] + """\',
                        RT_lat = \'""" + data['RT_lat'] + """\',
                        RB_long = \'""" + data['RB_long'] + """\',
                        RB_lat = \'""" + data['RB_lat'] + """\'
                        WHERE zone_uid = \'""" + data['zone_uid'] + """\';
                        """

                #print(query)

                items = execute(query, 'post', conn)

                print(items)

                if items['code'] != 281:
                    items['message'] = 'check sql query to update zones'
                return items

            elif action == 'get':
                query = """
                        SELECT * FROM M4ME.zones;
                        """

                items = execute(query, 'get', conn)
                if items['code'] != 280:
                    items['message'] = 'check sql query for get request'
                return items

            else:
                return 'choose correct option'

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class meal_type (Resource):
    def get(self):
        try:
            conn = connect()
            
            query = """
                    SELECT distinct meal_category
                    FROM meals
                    order by meal_category;
                    """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting meal types")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')


class payment_info (Resource):
    def get(self, p_id):
        try:
            conn = connect()
            
            query = """
                    SELECT *
                    FROM payments
                    WHERE payment_uid = \'""" + p_id + """\';
                    """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting payment info")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')


class payment_info_history (Resource): #edit to take in purchase_uid
    def get(self, p_id):
        try:
            conn = connect()
            
            query = """
                    SELECT *
                    FROM purchases
                    inner join payments
                        on purchase_id = pay_purchase_id
                    WHERE purchase_id = \'""" + p_id + """\';
                    """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting payment info")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')



class Meals_Selected_pid(Resource):
    def get(self):
        try:
            conn = connect()
            purchase_id = request.args['purchase_id']
            query = """
                    # CUSTOMER QUERY 3: ALL MEAL SELECTIONS BY CUSTOMER  (INCLUDES HISTORY)
                    SELECT * FROM M4ME.latest_combined_meal lcm
                    LEFT JOIN M4ME.lplp
                        ON lcm.sel_purchase_id = lplp.purchase_id
                    WHERE purchase_id = '""" + purchase_id + """'; 
                    """

            
            items = execute(query, 'get', conn)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Meals selected"
                items['code'] = 200
                #return items
            return items


            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class orders_by_business_specific(Resource): #need to fix

    def get(self, b_id):

        try:
            conn = connect()
            query = """
                    SELECT *,deconstruct.* 
                    FROM M4ME.lplp, 
                         JSON_TABLE(items, '$[*]' COLUMNS (
                                    qty VARCHAR(255)  PATH '$.qty',
                                    name VARCHAR(255)  PATH '$.name',
                                    price VARCHAR(255)  PATH '$.price',
                                    item_uid VARCHAR(255)  PATH '$.item_uid',
                                    itm_business_uid VARCHAR(255) PATH '$.itm_business_uid')
                         ) AS deconstruct
                    WHERE itm_business_uid = '""" + b_id + """';  
                    """
            items = execute(query, 'get', conn)
            if items['code'] == 280:
                items['message'] = 'Orders by business view loaded successful'
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
            return items
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class Orders_by_Purchase_Id_with_Pid(Resource):
    def get(self, p_id):
        response = {}
        items = {}
        try:
            conn = connect()
            query = """
                    SELECT
                        d_menu_date,
                        d_purchase_id,
                        group_concat(jt_name),
                        group_concat(jt_qty)
                    FROM fcs_items_by_row
                    where d_purchase_id = \'""" + p_id + """\' and lplpibr_purchase_status = "ACTIVE"
                    group by d_purchase_id, d_menu_date
                    order by d_menu_date desc;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class Orders_by_Purchase_Id_with_Pid_and_date(Resource):
    def get(self, p_id, date):
        response = {}
        items = {}
        try:
            conn = connect()
            query = """
                    SELECT
                        d_menu_date,
                        d_purchase_id,
                        group_concat(jt_name),
                        group_concat(jt_qty)
                    FROM fcs_items_by_row
                    where d_purchase_id = \'""" + p_id + """\' and d_menu_date = \'""" + date + """\'
                    group by d_purchase_id, d_menu_date;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class Orders_by_Items_total_items(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    select d_menu_date,
                            jt_name,
                            sum(jt_qty)
                    FROM fcs_items_by_row
                    group by jt_name, d_menu_date
                    order by d_menu_date desc;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class categoricalOptions(Resource):
    def get(self, long, lat):
        response = {}
        items = {}

        try:
            conn = connect()
            print('IN')
            '''
            # query for businesses serving in customer's zone
            query = """
                    SELECT zone
                    FROM
                    (SELECT *,  
                    IF (
                    IF ((z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long) <= 0,
                    \'""" + lat + """\' >=  (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long) * \'""" + long + """\' + z.LT_lat - z.LT_long * (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long),
                    \'""" + lat + """\' <=   (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long) * \'""" + long + """\' + z.LT_lat - z.LT_long * (z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long)) AND
                           
                    \'""" + lat + """\' <= (z.RT_lat - z.LT_lat)/(z.RT_long - z.LT_long) * \'""" + long + """\' + z.RT_lat - z.RT_long * (z.RT_lat - z.LT_lat)/(z.RT_long - z.LT_long) AND
                           
                    IF ((z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long) >= 0,  
                    \'""" + lat + """\' >= (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long) * \'""" + long + """\' + z.RB_lat - z.RB_long * (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long),
                    \'""" + lat + """\' <= (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long) * \'""" + long + """\' + z.RB_lat - z.RB_long * (z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long)) AND
                           
                    \'""" + lat + """\' >= (z.LB_lat - z.RB_lat)/(z.LB_long - z.RB_long) * \'""" + long + """\' + z.LB_lat - z.LB_long * (z.LB_lat - z.RB_lat)/(z.LB_long - z.RB_long), "TRUE", "FALSE") AS "In_Zone",
                     
                    FORMAT((z.LT_lat - z.LB_lat)/(z.LT_long - z.LB_long),3) AS "LEFT_SLOPE",
                    FORMAT((z.RB_lat - z.RT_lat)/(z.RB_long - z.RT_long),3) AS "RIGHT_SLOPE"
                    FROM zones z) AS DD
                    WHERE In_Zone = 'True'
                    ;
                    """
                
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'check sql query'
                return items
            print(items)
            for vals in items['result']:
                zones.append(vals['zone'])
            '''
            print('START')
            zones = ['Random', 'Random']
            query = """
                    SELECT * from zones;
                  """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'check sql query'
                return items

            for vals in items['result']:
                LT_long = vals['LT_long']
                LT_lat = vals['LT_lat']
                LB_long = vals['LB_long']
                LB_lat = vals['LB_lat']
                RT_long = vals['RT_long']
                RT_lat = vals['RT_lat']
                RB_long = vals['RB_long']
                RB_lat = vals['RB_lat']


                point = Point(float(long),float(lat))
                polygon = Polygon([(LB_long, LB_lat), (LT_long, LT_lat), (RT_long, RT_lat), (RB_long, RB_lat)])
                res = polygon.contains(point)
                print(res)

                if res:
                    zones.append(vals['zone'])


            print('ZONES-----', zones)
            query = """
                    SELECT      
                    rjzjt.zone_uid,
                    rjzjt.zone,
                    rjzjt.zone_name,
                    rjzjt.z_id,
                    rjzjt.z_biz_id,
                    b.business_name,
                    rjzjt.z_delivery_day,
                    rjzjt.z_delivery_time,
                    rjzjt.z_accepting_day,
                    rjzjt.z_accepting_time,
                    rjzjt.LB_long,rjzjt.LB_lat,rjzjt.LT_long,rjzjt.LT_lat,rjzjt.RT_long,rjzjt.RT_lat,rjzjt.RB_long,rjzjt.RB_lat,
                    b.business_type,
                    b.business_image,
                    b.business_accepting_hours,
                    rjzjt.tax_rate,
                    rjzjt.service_fee,
                    rjzjt.delivery_fee
                    FROM businesses b
                    RIGHT JOIN
                    (SELECT *
                         FROM zones AS z,
                         json_table(z_businesses, '$[*]'
                             COLUMNS (
                                    z_id FOR ORDINALITY,
                                    z_biz_id VARCHAR(255) PATH '$')
                                                 ) as zjt) as rjzjt
                    ON b.business_uid = rjzjt.z_biz_id
                    WHERE zone IN """ + str(tuple(zones)) + """;
                    """
            items = execute(query, 'get', conn)

            if items['code'] != 280:
                items['message'] = 'check sql query'
            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

# class cancel_purchase (Resource):
#     def put(self):
#         try:
#             print("00")
#             conn = connect()
#             response = {}
#             response2 = {}
#             response3 = {}
#             data = request.get_json(force=True)
#             purchaseID = data["purchase_uid"]
#             print(data)
#             print("0")
#             info_query = """
#                         SELECT pur.*, pay.*, sub.*
#                         FROM purchases pur, payments pay, subscription_items sub
#                         WHERE pur.purchase_uid = pay.pay_purchase_uid
#                             AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
#                                                     FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
#                             AND pur.purchase_uid = '""" + purchaseID + """'
#                             AND pur.purchase_status='ACTIVE';
#                         """
#             info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
#             if info_res[1] != 200:
#                 return {"message": "Internal Server Error"}, 500
#             # Calculate refund
#             print(info_res)
#             print("1")
#             refund_info = Change_Purchase().refund_calculator(info_res[0]['result'][0], conn)
#             print("2")
#             print(refund_info)
#             refund_amount = refund_info['refund_amount']
#             print(refund_amount)
#             if refund_amount > 0:
#                 print("2.3")
#                 # establishing more info for refund_info before we feed it in stripe_refund
#                 refund_info['refund_amount'] = abs(refund_amount)
#                 print("2.33")
#                 refund_info['purchase_uid'] = purchaseID
#                 print("2.36")
#                 print(refund_info)
#                 refund_info['refunded_id'] = Change_Purchase().stripe_refund(refund_info, conn)
#                 print("2.4")
#                 if refund_info['refunded_id'] is not None:
#                     refunded = True
#                 else:
#                     return {"message": "REFUND PROCESS ERROR."}, 500
#             print("2.5")
#             query = """
#                     Update M4ME.purchases
#                     set 
#                         purchase_status = "CANCELLED and REFUNDED"
#                     where purchase_uid = '""" + purchaseID + """';
#                     """
#             response = execute(query, 'post', conn)
#             print("3")
#             print(response)
#             if response['code'] != 281:
#                 return {"message": "Internal Server Error"}, 500
#             print("3.3")
#             new_paymentId = get_new_paymentID(conn)
#             print("3.4")
#             if new_paymentId[1] == 500:
#                 print(new_paymentId[0])
#                 response['message'] = "Internal Server Error."
#                 return response, 500
#             print("3.5")
#             print(refund_amount)
#             new_refund = 0-abs(refund_amount)
            
#             new_refund = str(new_refund)
#             print("3.6")
#             #print(info_res["result"][2])
#             print(type(new_refund))
#             print(new_refund)
#             #print(refund_info["refunded_id"][0])
#             refund_id = str(refund_info["refunded_id"][0])
#             #print(refund_id)
#             print("3.65")
#             print("start input")
#             print(new_paymentId)
#             print(purchaseID)
#             print(new_refund)
#             print(refund_id)
#             print("end input")
#             payment_query = """
#                     insert into payments(payment_uid, payment_id, pay_purchase_uid, pay_purchase_id, payment_time_stamp, amount_due, amount_paid, charge_id, payment_type, cc_num, cc_exp_date, cc_cvv, cc_zip)
#                     values(
#                         '""" + new_paymentId + """',
#                         '""" + new_paymentId + """',
#                         '""" + purchaseID + """',
#                         (
#                             select purchase_id
#                             from purchases
#                             where purchase_uid = '""" + purchaseID + """'
#                             order by purchase_date desc
#                             limit 1
#                         ),
#                         now(),
#                         '""" + new_refund + """',
#                         '""" + new_refund + """',
#                         '""" + refund_id + """',
#                         "STRIPE",
#                         (
#                             select cc_num
#                             from lplp
#                             where purchase_uid = '""" + purchaseID + """'
#                             order by payment_time_stamp desc
#                             limit 1
#                         ),
#                         (
#                             select cc_exp_date
#                             from lplp
#                             where purchase_uid = '""" + purchaseID + """'
#                             order by payment_time_stamp desc
#                             limit 1
#                         ),
#                         (
#                             select cc_cvv
#                             from lplp
#                             where purchase_uid = '""" + purchaseID + """'
#                             order by payment_time_stamp desc
#                             limit 1
#                         ),
#                         (
#                             select cc_zip
#                             from lplp
#                             where purchase_uid = '""" + purchaseID + """'
#                             order by payment_time_stamp desc
#                             limit 1
#                         )
#                     );
#                     """
#             print("3.7")
#             response2 = execute(payment_query, 'post', conn)
#             print("4")
#             print(response2)
#             if response2['code'] != 281:
#                 return {"message": "Internal Server Error"}, 500
#             print("4.5")
#             cancel_query = """
#                     update purchases
#                     set cancel_date = now()
#                     where purchase_uid = '""" + purchaseID + """';
#                     """
#             print("4.7")
#             print(cancel_query)
#             response2 = execute(cancel_query, 'post', conn)
#             print("5")
#             print(response2)
#             if response2['code'] != 281:
#                 print("6")
#                 return {"message": "Internal Server Error"}, 500
#             print("7")
#             return response2

#         except:
#             raise BadRequest("Request failed, please try again later.")
#         finally:
#             disconnect(conn)


class get_Zones_specific (Resource):
    def get(self, lat, long):
        try:
            conn = connect()
            
            query = """
                    SELECT *
                    FROM M4ME.zones
                    where lat > LB_lat
                    and lat < LT_lat
                    and lat > RB_lat
                    and lat < RT_lat
                    and long > LB_long
                    and long < RB_long
                    and long > LT_long
                    and long < RT_long;
                    """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting zones")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')


class find_next_sat (Resource):
    def get(self):
        try:
            #conn = connect()
            print("1")
            d = date.today() # Monday
            print("2")
            t = timedelta((12 - d.weekday()) % 7)
            d + t
            datetime.datetime(2013, 6, 1, 0, 0)
            date = str((d + t).strftime('%Y-%m-%d'))
            return date
        except:
            print("error")
        finally:
            #disconnect(conn)
            print("done")


class get_final_price (Resource):
    def get(self):
        try:
            conn = connect()
            purchase_uid = data["p_uid"]
            data = request.get_json(force=True)
            query = {

            }
            return date
        except:
            print("error")
        finally:
            #disconnect(conn)
            print("done")



class Get_Latest_Purchases_Payments_with_Refund(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            #purchase_uid = request.args['purchase_uid']
            query = """
                    # CUSTOMER QUERY 2: CUSTOMER LATEST PURCHASE AND LATEST PAYMENT HISTORY
                    # NEED CUSTOMER ADDRESS IN CASE CUSTOMER HAS NOT ORDERED BEFORE
                    SELECT * FROM M4ME.lplp lp
                    LEFT JOIN M4ME.customers c
                        ON lp.pur_customer_uid = c.customer_uid
                    WHERE pur_customer_uid = '""" + customer_uid + """'
                    and items like "%200-000002%"
                    and purchase_status = "ACTIVE";
                    """
            response = simple_get_execute(query, __class__.__name__, conn)
            if response[1] != 200:
                return response[1]
            except_list = ['password_hashed', 'password_salt', 'password_algorithm']
            for i in range(len(response[0]['result'])):
                for key in except_list:
                     if response[0]['result'][i].get(key) is not None:
                        del response[0]['result'][i][key]
            refundinfo = {}
            print("here")
            intx=0
            for i2 in range(len(response[0]['result'])):
                print("here 1")
                print(response[0]['result'][intx]["purchase_uid"])
                info_query = """
                       SELECT pur.*, pay.*, sub.*
                       FROM purchases pur, payments pay, subscription_items sub
                       WHERE pur.purchase_uid = pay.pay_purchase_uid
                           AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
                                                   FROM purchases WHERE purchase_uid = '""" + response[0]['result'][i2]["purchase_uid"] + """')
                           AND pur.purchase_uid = '""" + response[0]['result'][i2]["purchase_uid"] + """'
                           AND pur.purchase_status='ACTIVE';  
                       """
                info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
                refund_info = Change_Purchase().refund_calculator(info_res[0]['result'][0], conn)

                refundinfo[intx]=refund_info
                intx=intx+1
            response2 = {}
            inty = 0
            print("changes here")
            for i2 in range(len(response[0]['result'])):
                #print(response[0]['result'][i2])
                response2[inty]=str(response[0]['result'][i2]) + "" + str(refundinfo[i2])
                print("1")
                #inty=inty+1
                #print(refundinfo[i2])
                #response2[inty+1]=refundinfo[i2]
                print("2")
                inty=inty+1
            print("here 3")
            print(response2)
            return response2
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class payment_info_history_fixed (Resource): #edit to take in purchase_uid
    def get(self, p_uid):
        try:
            conn = connect()
            
            query = """
                    SELECT *
                    FROM purchases
                    inner join payments
                        on purchase_id = pay_purchase_id
                    WHERE purchase_id = (select pay_purchase_id from payments where pay_purchase_uid = \'""" + p_uid + """\');
                    """
            items = execute(query, 'get', conn)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting payment info")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')

#if one is changed to skip, add extra surprise. if skip is changed to surprise, delete newest surprise
class add_surprise (Resource):
    def post(self, p_uid):
        try:
            conn = connect()
            # query = """
            #         select num_issues 
            #         from subscription_items
            #         where item_price=
            #         (SELECT json_extract(items, '$[0].price') price
            #         FROM purchases WHERE purchase_uid = \'""" + p_uid + """\');
            #         """

            query = """
                    
                    SELECT json_extract(items, '$[0].qty') as qty
                    FROM purchases WHERE purchase_uid = \'""" + p_uid + """\';
                    """
            items = execute(query, 'get', conn)
            print(items)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            #print(int(items["result"][0]["num_issues"]))
            print("1")
            query1 ="""
                        select purchase_id
                        from purchases
                        where purchase_uid = \'""" + p_uid + """\';
                    """
            print("1.5")
            p_id = execute(query1, 'get', conn)
            print("1.7")
            tempstring = items["result"][0]["qty"].strip('\"')
            inty=int(tempstring)
            print(inty)
            intx=0

            print("2")
            query3 ="""
                        select distinct menu_date
                        from menu
                        where menu_date > now()
                        order by menu_date asc;
                    """
            print("3")
            menu_date = execute(query3, 'get', conn)
            intx=0
            print(menu_date['result'][intx]['menu_date'])
            for intx in range(0,inty):
                res = execute("CALL new_meals_selected_uid();", 'get', conn)
                print("4")
                print(intx)
                #temparr= str(menu_date['result'][intx]['menu_date'])
                #print(temparr)
                print(p_id)
                query2 ="""
                            insert into meals_selected (selection_uid, sel_purchase_id, selection_time, sel_menu_date, meal_selection, delivery_day)
                            values(
                                \'""" + res['result'][0]['new_id'] + """\',
                                \'""" + p_id["result"][0]["purchase_id"] + """\',
                                now(),
                                \'""" + menu_date['result'][intx]['menu_date'] + """\',
                                '[{
                                    "qty": "", 
                                    "name": "SURPRISE", 
                                    "price": "", 
                                    "item_uid": ""
                                }]',
                                "SUNDAY"
                            );
                        """
                print("5")
                sur_item = execute(query2, 'post', conn)
                print(sur_item)
                print("6")
                # query3= """
                #             update meals_selected
                #             set
                #             sel_menu_date = '""" + menu_date['result'][intx]['menu_date'] + """'
                #             where selection_uid = \'""" + res['result'][0]['new_id'] + """\';
                #         """
                # udate = execute(query3, 'post', conn)
                print("7")
            return sur_item
        except:
                print("Error happened while getting payment info")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')



class discount_percentage (Resource): #edit to take in purchase_uid
    def get(self, n_delivery):
        try:
            conn = connect()
            query = """
                    SELECT *
                    FROM discounts
                    WHERE num_deliveries = \'""" + n_delivery + """\';
                    """
            items = execute(query, 'get', conn)
            print(items)
            if items['code'] != 280:
                items['message'] = 'Check sql query'
                return items
            #items['result'] = items['result'][0]
            return items
        except:
                print("Error happened while getting discount info")
                raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('process completed')

class Copy_Menu(Resource):

    def post(self):
        # date1 and date2 are passed from json body
        # (params should be called date1 and date2)
        # example: {"date1" = "2020-10-03 00:00:00", "date2" = "2020-10-12 00:00:00"}
        # goal: copy the menu items from date1 to date2 (we can use INSERT INTO command)
        # query: with dates passed from json body we can get the rows from the database
        # containing date1, iterate through these rows to give them a new menu_uid and update 
        # the menu_date to date2. We also have to insert the new row one at a time because to
        # generate a new menu_uid each time, we have to insert the row with the most recently
        # generated new menu_uid to get a new one for the next row to be inserted
        try:
            conn = connect()
            dates = request.get_json(force=True)
            copyFromDate = dates['date1']
            copyToDate = dates['date2']
            query = """ SELECT * FROM M4ME.menu WHERE menu_date = \'""" + copyFromDate + """\'; """
            items = execute(query, 'get', conn)
            records = items['result']
            
            for i in range(len(records)):
                newIdQuery = """ call M4ME.new_menu_uid(); """
                newId = execute(newIdQuery, 'get', conn)
                newMenuUid = newId['result'][0]['new_id']
                #print(newMenuUid)
                date = copyToDate
                #print(date)
                category = records[i]['menu_category']
                #print(category)
                menuType = records[i]['menu_type']
                #print(menuType)
                cat = records[i]['meal_cat']
                #print(cat)
                menuMealId = records[i]['menu_meal_id']
                #print(menuMealId)
                defaultMeal = records[i]['default_meal']
                #print(defaultMeal)
                deliveryDays = records[i]['delivery_days']
                #print(deliveryDays)
                price = records[i]['meal_price']
                #print(price)
                postQuery = """ INSERT INTO 
                                M4ME.menu (menu_uid, menu_date, menu_category, menu_type, meal_cat, 
                                           menu_meal_id, default_meal, delivery_days, meal_price) 
                                VALUES (\'""" + str(newMenuUid) + """\', \'""" + str(date) + """\', \'""" + str(category) + """\', 
                                        \'""" + str(menuType) + """\', \'""" + str(cat) + """\', \'""" + str(menuMealId) + """\', 
                                        \'""" + str(defaultMeal) + """\', \'""" + str(deliveryDays) + """\', \'""" + str(price) + """\'); """
                #print(postQuery)
                copiedRow = execute(postQuery, 'post', conn)
        except:
            print('Error has occurred trying to copy menu items')
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
            print('Process completed')


# Parva Code  -----------------------------------------------------------------------------------------------------------

class change_purchase(Resource):
    def get(self, purchaseID):
        
        conn = connect()
        info_query = """
                        SELECT pur.*, pay.*, sub.*
                        FROM purchases pur, payments pay, subscription_items sub
                        WHERE pur.purchase_uid = pay.pay_purchase_uid
                            AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid
                                                    FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
                            AND pur.purchase_uid = '""" + purchaseID + """'
                            AND pur.purchase_status='ACTIVE';  
                        """
        print("info_query", info_query)
        info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
        print(info_res)
        if info_res[1] != 200:
            return {"message": "Internal Server Error"}, 500
        # Calculate refund
        print("1.9")
        refund_info = self.new_refund_calculator(info_res[0]['result'][0], conn)

        return refund_info

    def post(self, purchaseID):
        try:
            conn = connect()
            #response = {}
            charge_id = None
            refunded = False
            refund_ui = None
            # For this update_purchase endpoint, we should consider to ask customer provide their identity to make sure the right
            # person is doing what he/she want.
            # Also, using POST to protect sensitive information.
            data = request.get_json(force=True)
            customer_email = data['customer_email']
            #password = data.get('password')
            refresh_token = data.get('refresh_token')
            cc_num = str(data['cc_num'])
            cc_exp_date = data['cc_exp_date']
            #cc_exp_date = data['cc_exp_year'] + data['cc_exp_month'] + "01"
            cc_cvv = data['cc_cvv']
            cc_zip = data['cc_zip']
            purchaseID = data['purchase_id']
            new_item_id = data['new_item_id']
            #customer_uid = data["customer_id"]
            items = "'[" + ", ".join([str(item).replace("'", "\"") if item else "NULL" for item in data['items']]) + "]'"
            print(items)
            print("1")
            #Check user's identity
            # cus_query = """
            #             SELECT password_hashed,
            #                     user_refresh_token, customer_phone_num
            #             FROM customers
            #             WHERE customer_email = '""" + customer_email + """';
            #             """
            # cus_res = simple_get_execute(cus_query, "Update_Purchase - Check Login", conn)
            # if cus_res[1] != 200:
            #     return cus_res
            # customer_phone_num = cus_res[0]['result'][0]['customer_phone_num']
            # if not password and not refresh_token:
            #     raise BadRequest("Request failed, please try again later.")
            # elif password:
            #     if password != cus_res[0]['result'][0]['password_hashed']:
            #         response['message'] = 'Wrong password'
            #         return response, 401
            # elif refresh_token:
            #     if refresh_token != cus_res[0]['result'][0]['mobile_refresh_token']:
            #         response['message'] = 'Token Invalid'
            #         return response, 401
            print("1.5")
            # query info for requesting purchase
            # Get info of requesting purchase_id
            info_query = """
                        SELECT pur.*, pay.*, sub.*
                        FROM purchases pur, payments pay, subscription_items sub
                        WHERE pur.purchase_uid = pay.pay_purchase_uid
                            AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid
                                                    FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
                            AND pur.purchase_uid = '""" + purchaseID + """'
                            AND pur.purchase_status='ACTIVE';  
                        """
            info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
            print(info_res)
            if info_res[1] != 200:
                return {"message": "Internal Server Error"}, 500
            # Calculate refund
            print("1.9")
            refund_info = self.new_refund_calculator(info_res[0]['result'][0], conn)
            print("2")
            refund_amount = refund_info['refund_amount']



            temp_key = ""
            if stripe.api_key is not None:
                temp_key = stripe.api_key
            if info_res[0]['result'][0]["delivery_instructions"] == "M4METEST":
                stripe.api_key = stripe_secret_test_key #"sk_test_51HyTqpGkl299bo00yD1lTRNK"
                print('TEST')
            else:
                stripe.api_key = stripe_secret_live_key
                print('LIVE')




            # price for the new purchase
            # this query below for querying the price may be redundant, the front end can send it in data['items']
            # Should we do it here to make sure that the front end did not make any error?

            print("start probelm here")
            #####################
            num_meals = data["items"][0]["name"][0]
            print("meals :",num_meals)
            # # get number of days
            num_days = data["items"][0]["qty"]
            
            print("days :", num_days)

            # price = (json.loads(info_res['items'])[0].get('price'))

            # print("price :", price)
            ####################


            delivery_query= """
                            select item_price, delivery_discount from subscription_items si
                            join discounts
                            where itm_business_uid = "200-000002"
                            and si.num_items = '""" + num_meals + """' 
                            and num_deliveries = '""" + num_days + """';
                        """
            d_query = simple_get_execute(delivery_query, 'get', conn)
            print("2")
            print(d_query[0]["result"][0]["item_price"])
            price = int(d_query[0]["result"][0]["item_price"])
            print(price)
            discount = int(d_query[0]["result"][0]["delivery_discount"])
            print("3")
            customer_used_amount = int(num_days)*price*(1-discount/100)
            print(refund_info["refund_amount"])
            print("customer_used_amount " + str(customer_used_amount))
            print("refund_info " + str(refund_info["refund_amount"]))
            amount_will_charge = customer_used_amount - refund_info["refund_amount"]
            print("amount will charge " + str(amount_will_charge))
            # Process stripe
            print("start here 1")
            print(amount_will_charge)
            if amount_will_charge > 0:
                #charge with stripe
                #wrap credit_card info
                query = '''SELECT cc_num, cc_cvv, cc_zip, cc_exp_date
                                FROM M4ME.payments
                                WHERE pay_purchase_uid = "''' + purchaseID + '";'
                res = simple_get_execute(query, "GET CREDIT CARD INFO FOR CHANGING MEAL PLAN", conn)
                print("continue here 1")
                if res[1] != 200:
                    return {"message": "Cannot collect credit card info"}, 500

                [cc_num, cc_cvv, cc_exp_date, cc_zip] = destructure(res[0]['result'][0], "cc_num",  "cc_cvv", "cc_exp_date", "cc_zip")

                month = cc_exp_date.split("-")[1]
                year  = cc_exp_date.split("-")[0]
                print("continue here 1.5")
                card_dict = {"number": cc_num, "exp_month": int(month), "exp_year": int(year), "cvc": cc_cvv}
                print("continue here 1.6")
                try:
                    print("start card error")
                    card_token = stripe.Token.create(card=card_dict)
                    print("card error 1")
                    charge_id = stripe.Charge.create(
                        amount=int(amount_will_charge * 100),
                        currency="usd",
                        source=card_token,
                        description="Charge for changing Meal Plan",
                    )
                    print("card error 2")
                except stripe.error.CardError as e:
                    # Since it's a decline, stripe.error.CardError will be caught
                    response['message'] = e.error.message
                    return response, 400
                print("continue here 2")
            elif amount_will_charge < 0:
                # establishing more info for refund_info before we feed it in stripe_refund
                refund_info['refund_amount'] = abs(amount_will_charge)
                refund_info['purchase_uid'] = purchaseID
                refund_info['refunded_id'] = self.stripe_refund(refund_info, conn)
                print("end stripe refund")

                ###
                if refund_info['refunded_id'] is not None:
                    refunded = True
                else:
                    return {"message": "REFUND PROCESS ERROR."}, 500



            #gathering data before writting info to database
            # need to calculate the start_delivery_date
            dayOfWeek = datetime.now().weekday()

                # Get the soonest Thursday, same day if today is Thursday
            thurs = datetime.now() + timedelta(days=(3 - dayOfWeek) % 7)

                # If today is Thursday after 4PM'
            if thurs.date() == datetime.now().date() and datetime.now().hour >= 16:
                thurs += timedelta(days=7)

                #the next saturday
            start_delivery_date = (thurs + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            print("start here 5")
            #print(stop)
            charge_id = "'" + charge_id.id + "'" if charge_id else "NULL"
            info_res = info_res[0]['result'][0]

            payment_id = info_res.get("payment_id")
            purchase_id = info_res.get("purchase_id")
            customer_uid = info_res.get("pur_customer_uid")
            delivery_first_name = info_res.get("delivery_first_name")
            delivery_last_name = info_res.get("delivery_last_name")
            delivery_email = info_res.get("delivery_email")
            delivery_phone = info_res.get("delivery_phone_num")
            delivery_address = info_res.get("delivery_address")
            delivery_unit = info_res.get("delivery_unit")
            delivery_city = info_res.get("delivery_city")
            delivery_state = info_res.get("delivery_state")
            delivery_zip = info_res.get("delivery_zip")
            delivery_instructions = info_res.get("delivery_instructions") if info_res.get('delivery_instruction') else "NULL"
            delivery_longitude = info_res.get("delivery_longitude")
            delivery_latitude = info_res.get("delivery_latitude")
            order_instructions = info_res.get("order_instructions") if info_res.get("order_instructions") else "NULL"
            purchase_notes = info_res.get("purchase_notes") if info_res.get("purchase_notes") else "NULL"
            # get the new ids
            print("writting into database")
            purchase_uid = get_new_purchaseID(conn)
            if purchase_uid[1] == 500:
                print(purchaseId[0])
                return {"message": "Internal Server Error."}, 500
            payment_uid = get_new_paymentID(conn)
            if payment_uid[1] == 500:
                print(payment_uid[0])
                return {"message": "Internal Server Error."}, 500
            # write the new purchase_id and payment_id into database
                # write into Payments table
            queries = [
                '''
                INSERT INTO M4ME.payments
                SET payment_uid = "''' + payment_uid + '''",
                                        payment_time_stamp = "''' + getNow() + '''",
                                        start_delivery_date = "''' + start_delivery_date + '''",
                                        payment_id = "''' + payment_id + '''",
                                        pay_purchase_id = "''' + purchase_id + '''",
                                        pay_purchase_uid = "''' + purchase_uid + '''",
                                        amount_due = "''' + str(round(amount_will_charge,2)) + '''",
                                        amount_discount = 0,
                                        amount_paid = "''' + str(round(amount_will_charge,2)) + '''",
                                        pay_coupon_id = NULL,
                                        charge_id = ''' + charge_id + ''',
                                        payment_type = NULL,
                                        info_is_Addon = "FALSE",
                                        cc_num = "''' + str(cc_num) + '''",
                                        cc_exp_date = "''' + str(cc_exp_date) + '''",
                                        cc_cvv = "''' + str(cc_cvv) + '''",
                                        cc_zip = "''' + str(cc_zip) + '''";
                ''',
                '''
                INSERT INTO  M4ME.purchases
                SET purchase_uid = "''' + purchase_uid + '''",
                                        purchase_date = "''' + getNow() + '''",
                                        purchase_id = "''' + purchase_id + '''",
                                        purchase_status = 'ACTIVE',
                                        pur_customer_uid = "''' + customer_uid + '''",
                                        delivery_first_name = "''' + delivery_first_name + '''",
                                        delivery_last_name = "''' + delivery_last_name + '''",
                                        delivery_email = "''' + delivery_email + '''",
                                        delivery_phone_num = "''' + str(delivery_phone) + '''",
                                        delivery_address = "''' + delivery_address + '''",
                                        delivery_unit = "''' + str(delivery_unit) + '''",
                                        delivery_city = "''' + delivery_city + '''",
                                        delivery_state = "''' + delivery_state + '''",
                                        delivery_zip = "''' + str(delivery_zip) + '''",
                                        delivery_instructions = "''' + delivery_instructions + '''",
                                        delivery_longitude = "''' + delivery_longitude + '''",
                                        delivery_latitude = "''' + delivery_latitude + '''",
                                        items = ''' + items + ''',
                                        order_instructions = "''' + order_instructions + '''",
                                        purchase_notes = "''' + purchase_notes + '''";'''
            ]
            if refunded:  # if refunded is true then write it to refund table
                res_refund_uid = get_new_id("CALL new_refund_uid", "GET NEW REFUND UID", conn)
                if res_refund_uid[1] != 200:
                    return {"message": "Error happened when requesting new refund_uid"}, 500
                refund_uid = res_refund_uid[0]['result']
                print("refund_uid: ", refund_uid)

                query = '''INSERT INTO M4ME.refunds
                                    SET refund_uid = "''' + refund_uid + '''",
                                        created_at = "''' + getNow() + '''",
                                        email_id = "''' + customer_email + '''",
                                        phone_num = "''' + str(customer_phone_num) + '''",
                                        image_url = "NOT REQUIRED",
                                        customer_note = "NOT REQUIRED",
                                        admin_note = "CHANGED MEAL PLAN",
                                        refund_amount = "''' + str(abs(amount_will_charge)) + '";'
                print(query)
                refund_res = simple_post_execute([query], ["REFUND"], conn)
                print("refund_res: ", refund_res)
                if refund_res[1] != 201:
                    return {"message": "Error happened while writting into refund table"}, 500
            response = simple_post_execute(queries, ["PAYMENTS", "PURCHASES"], conn)


            if temp_key is not None:
                stripe.api_key = temp_key


            if response[1] == 201:
                if refunded:
                    response[0]['refund_uid'] = refund_uid
                response[0]['payment_id'] = payment_uid
                response[0]['purchase_id'] = purchase_uid
                query = '''UPDATE M4ME.purchases SET purchase_status = "CANCELLED" WHERE purchase_uid = "''' + purchaseID + '";'
                simple_post_execute([query], ["UPDATE OLD PURCHASES"], conn)

                return response

            else:
                if "payment_uid" in locals() and "purchase_uid" in locals():
                    execute("""DELETE FROM payments WHERE payment_uid = '""" + payment_uid + """';""", 'post', conn)
                    execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchase_uid + """';""", 'post',
                            conn)
                return {"message": "Internal Server Error."}, 500

        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)


    def stripe_refund (self, refund_info, conn):
        print("start stripe refund")
        refund_amount = refund_info['refund_amount']
        print("stripe 1")
        refund_id = []
        # retrieve charge info from stripe to determine how much refund amount left on current charge_id
        # if refund amount left on current charge_id < refund amount needed then trace back the latest previous payment
        # to get the next stripe_charge_id.
        #list all charge ids which are associated with current purchase_id
        query = '''SELECT charge_id from M4ME.payments
               WHERE pay_purchase_id = (SELECT pay_purchase_id FROM M4ME.payments
                                       WHERE pay_purchase_uid = "''' + refund_info['purchase_uid'] + '''")
                    ORDER BY payment_time_stamp DESC;'''
        res = simple_get_execute(query, "QUERY ALL CHARGE IDS FOR REFUND", conn)
        print(res)
        # print("res in stripe_refund: ", res)
        if not res[0]['result']:
            print("Cannot process refund. No charge id found")
            return {"message": "Internal Server Error"}, 500
        else:
            print ("stripe 2")
            #print(res[0]['result'][0]["charge_id"])
            # print(len(res[0]['result']))
            intx = 0
            charge_ids = {}
            inty = 0
            for intx in range(0,len(res[0]["result"])):
                if res[0]["result"][intx]["charge_id"] is not None:
                    charge_ids[inty] = res[0]["result"][intx]["charge_id"]
                    inty=inty+1
            #print(charge_ids)
            print(charge_ids)
            #charge_ids = [v for item in res[0]['result'] for v in item.values() if v]
            #print("charge id " + charge_ids[intx])
            amount_should_refund = round(refund_amount*100,0)
            # print("before while loop. Charge_id: {}, its length: {}".format(charge_ids,len(charge_ids)))
            inty=inty-1
            while len(charge_ids) > 0 and amount_should_refund > 0:
                # print("amount should refund: ", amount_should_refund)
                print("stripe3")
                print(len(charge_ids))
                #process_id = charge_ids.pop(0)
                process_id = charge_ids[inty]
                inty = inty - 1
                print(charge_ids)
                # print("processing id: ", process_id)
                # print("charge_ids: {}, its  length: {}".format(charge_ids, len(charge_ids)))
                #retrieve info from stripe for specific charge_id:
                print("during stripe: stripe 1")
                print(process_id)
                #print(stripe.Charge.retrieve("ch_1IO5g8LMju5RPMEvOeH4k6a3",))
                if process_id[:2] == "pi":
                    process_id = stripe.PaymentIntent.retrieve(process_id).get("charges").get("data")[0].get("id")
                    #print(refunded_info.get("charges").get("data")[0].get("id"))
                refunded_info = stripe.Charge.retrieve(process_id)
                print("stripe 2")
                print(refunded_info.get("amount"))
                print(refunded_info.get('amount_refunded'))
                print("start inputs")
                print(refunded_info['amount'])
                print(refunded_info['amount_refunded'])
                print("end inputs ")
                # print("refunded_info: ", refunded_info)
                # print("refunded_info.get('amount'): ", refunded_info.get('amount_refunded'))
                if refunded_info.get('amount') is not None and refunded_info.get('amount_refunded') is not None:
                    amount_could_refund = round(float(refunded_info['amount'] - refunded_info['amount_refunded']),0)
                    print(amount_could_refund)
                    print(amount_should_refund)
                    # print("amount_could_refund: ", amount_could_refund)
                    # print("amount_should_refund: ", amount_should_refund)
                    if amount_should_refund <= amount_could_refund:
                        # refund it right away => amount should be refund is equal refunded_amount
                        print("here")
                        try:
                            refund_res = stripe.Refund.create(
                                charge=process_id,
                                amount=int(amount_should_refund)
                            )
                        except stripe.error.CardError as e:
                            # Since it's a decline, stripe.error.CardError will be caught
                            response['message'] = e.error.message
                            return response, 400
                        # print("refund_res: ", refund_res)
                        amount_should_refund = 0
                    elif amount_could_refund==0:
                        print ("problem here")
                        continue
                    else:
                        # refund it and then calculate how much is left for amount_should_refund
                        try:
                            refund_res = stripe.Refund.create(
                                charge=process_id,
                                amount=int(amount_could_refund)
                            )
                            # print("before substraction")
                            # print(type(amount_should_refund))
                            # print(type(amount_could_refund))
                            amount_should_refund -= int(amount_could_refund)
                            # print("amount_should_refund after recalculate: ", amount_should_refund)
                        except stripe.error.CardError as e:
                            # Since it's a decline, stripe.error.CardError will be caught
                            response['message'] = e.error.message
                            return response, 400
                    refund_id.append(refund_res.get('id'))
            return refund_id









    def new_refund_calculator(self, info_res,  conn):

        
        print("in refund calculator")
        
        # checking skips new

        start_delivery_date = datetime.strptime(info_res['start_delivery_date'], "%Y-%m-%d %H-%M-%S")
        week_remaining = int(info_res['payment_frequency'])
        
        all_deliveries = """
                    SELECT COUNT(delivery_day) AS delivery_count FROM
                            (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM meals_selected
                                WHERE sel_purchase_id = '""" + info_res['purchase_id'] + """'
                                GROUP BY sel_menu_date) AS GB
                                INNER JOIN meals_selected S
                                ON S.sel_purchase_id = GB.sel_purchase_id
                                    AND S.sel_menu_date = GB.sel_menu_date
                                    AND S.selection_time = GB.max_selection_time
                    WHERE 
                        S.sel_menu_date >= '""" + start_delivery_date.strftime("%Y-%m-%d %H:%M:%S") + """'
                        AND S.sel_menu_date <= '""" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """'
                        AND delivery_day != 'SKIP'
                    ORDER BY S.sel_menu_date;
                    """
        print("here 1")
        delivered_num = execute(all_deliveries, "get", conn)
        if delivered_num['code'] != 280:
            return delivered_num
        delivered_num = int(delivered_num['result'][0].get('delivery_count')) if delivered_num['result'][0].get('delivery_count') else 0
        print("delivered_num :", delivered_num)


        # get number of meals from item name
        num_meals = int(json.loads(info_res['items'])[0].get('name')[0])
        print("meals :",num_meals)
        # get number of days
        num_days = int(json.loads(info_res['items'])[0].get('qty'))
        
        print("days :", num_days)

        price = (json.loads(info_res['items'])[0].get('price'))

        print("price :", price)

        serviceFee = info_res['service_fee']
        print("serviceFee :", serviceFee)

        driver_tip = info_res['driver_tip']
        print("driver_tip :", driver_tip)

        taxes = info_res['taxes']
        print("taxes :", taxes)

        delivery_fee = info_res['delivery_fee']
        print("delivery_fee :", delivery_fee)
        # get remaining days
        #delivered_num
        remaining_delivery_days = num_days - delivered_num 
        print("days reamin :",remaining_delivery_days)


        # if weeks remaining are 0 return 
        if remaining_delivery_days == 0:
            {"week_remaining": 0, "refund_amount": 0}


        # if remaining days are negative then it means there is some error 
        if remaining_delivery_days < 0:
            print("There is something wrong with the query to get info for the requested purchase.")
            response = {'message': "Internal Server Error."}
            return response, 500
        print("here 2")
        discount_query = """
                        SELECT * FROM M4ME.discounts;
                        """
        discount = execute(discount_query, 'get', conn)

        if discount['code'] != 280:
            return discount
        print("here 3")
        # get discount combinations in a dictionary
        discount_dict = {}

        # for val in discount['result']:
        #     discount_dict[(val['num_deliveries'],val['num_meals'])] = float(val['total_discount'])
        # print("here 4")
        # customer_paid = 12*num_meals*num_days*(1-discount_dict[(num_days,num_meals)])

        # customer_used_amount = 12*num_meals*delivered_num *(1-discount_dict[(delivered_num ,num_meals)])

        # refund_amount = customer_paid - customer_used_amount
        print(info_res["purchase_uid"])
        purchase_query = """
                        SELECT * FROM M4ME.payments
                        join purchases on pay_purchase_uid = purchase_uid
                        join subscription_items on item_uid = (SELECT json_extract(items, '$[0].item_uid') as item_uid
                                                        FROM purchases WHERE purchase_uid = '""" + info_res["purchase_uid"] + """')
                        where pay_purchase_uid = '""" + info_res["purchase_uid"] + """';
                        """
        pchase = execute(purchase_query, 'get', conn)
        #print(pchase["result"][0]["items"][1])
        

        # queryn1:"""
        #             SELECT json_extract(items, '$[0].qty') as qty
        #             FROM purchases WHERE purchase_uid = '""" + info_res["purchase_uid"] + """'
        #         """
        # pchase = execute(queryn1, 'get', conn)
        #print(pchase["result"][0]["num_items"])
        #print(discount['result'])
        for val in discount['result']:
            discount_dict[(val['num_deliveries'])] = float(val['delivery_discount'])
        print("here 4")
        #print(pchase["result"][0]["num_items"])
        print("number of days " + str(num_days))
        strdays = str(num_days)
        print("number of meals " + str(num_meals))
        strmeal = str(num_meals)
        #print(info_res)
        delivery_query = """
                    select item_price, delivery_discount from subscription_items si
                    join discounts
                    where itm_business_uid = "200-000002"
                    and si.num_items = '""" + strmeal + """' 
                    and num_deliveries = '""" + strdays + """';
                    """
        d_query = execute(delivery_query, 'get', conn)
        print("here 4.5")
        print(d_query)
        old_discount = d_query["result"][0]["delivery_discount"]
        #old_price = d_query["result"][0]["item_price"]


        serviceFee = info_res['service_fee']
        print("serviceFee :", serviceFee)
        if serviceFee is None:
            serviceFee = 0
        driver_tip = info_res['driver_tip']
        print("driver_tip :", driver_tip)
        if driver_tip is None:
            driver_tip = 0
        taxes = info_res['taxes']
        print("taxes :", taxes)
        if taxes is None:
            taxes = 0
        delivery_fee = info_res['delivery_fee']
        print("delivery_fee :", delivery_fee)
        if delivery_fee is None:
            delivery_fee = 0
        #tax rate is base price only
        #driver tip and delivery fee are both percentage
        customer_paid = (float(price)*int(num_days)*(1-old_discount/100)) * 1 + float(taxes) + float(serviceFee) + float(driver_tip) + float(delivery_fee)
        print("4.6")
        print("customer paid " + str((float(price)*int(num_days)*(1-old_discount/100)) * 1 + float(taxes) + float(serviceFee) + float(driver_tip) + float(delivery_fee)))

        print("here 4.7")
        #print(d_query["result"][0]["item_price"])
        new_price = (d_query["result"][0]["item_price"])
        print(new_price)
        d_num = str(delivered_num)
        print(delivered_num)





        if delivered_num==0:
            customer_used_amount = 0
        elif delivered_num != 0:
            print("here 5")
            delivery_query2 = """
                                select delivery_discount from subscription_items si
                                join discounts
                                where itm_business_uid = "200-000002"
                                and si.num_items = '""" + strmeal + """' 
                                and num_deliveries = '""" + d_num + """';
                                """
            d2_query = execute(delivery_query2, 'get', conn)
            print("here 6")
            new_discount = d2_query["result"][0]["delivery_discount"]
            customer_used_amount = (delivered_num*new_price*(1-new_discount/100)) * 1+ float(taxes) + float(driver_tip)/delivered_num + float(delivery_fee)/delivered_num
        print("here 7")
        print(customer_used_amount)
        refund_amount = (float(customer_paid) - float(customer_used_amount))
        #print(refund_amount)
        print("refund amount " + str(round(refund_amount, 2)))
        #remaining_delivery_days = int(remaining_delivery_days)
        print("end refund calculator")
        return{"week_remaining": remaining_delivery_days, "refund_amount": float(str(round(refund_amount, 2)))}


class cancel_purchase(Resource):
    def put(self):
        try:
            print("00")
            conn = connect()
            response = {}
            response2 = {}
            refund_info = {}
            data = request.get_json(force=True)
            purchaseID = data["purchase_uid"]
            print(data)
            print("0")
            info_query = """
                        SELECT pur.*, pay.*, sub.*
                        FROM purchases pur, payments pay, subscription_items sub
                        WHERE pur.purchase_uid = pay.pay_purchase_uid
                            AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
                                                    FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
                            AND pur.purchase_uid = '""" + purchaseID + """'
                            AND pur.purchase_status='ACTIVE';
                        """
            
            info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
            print(info_res[0]['result'][0])
            if info_res[1] != 200:
                return {"message": "Internal Server Error"}, 500
            # Calculate refund
            print("1")


            print(info_res[0]['result'][0]["delivery_instructions"])
            temp_key = ""
            if stripe.api_key is not None:
                temp_key = stripe.api_key
            if info_res[0]['result'][0]["delivery_instructions"] == "M4METEST":
                #stripe.api_key = stripe_secret_test_key
                stripe.api_key = "sk_test_51HyqrgLMju5RPMEvowxoZHOI9LjFSxI9X3KPsOM7KVA4pxtJqlEwEkjLJ3GCL56xpIQuVImkSwJQ5TqpGkl299bo00yD1lTRNK"
                print('TEST')
            else:
                stripe.api_key = stripe_secret_live_key
                print('LIVE')
            print("try here 0")
            #refund_info = Change_Purchase().refund_calculator(info_res[0]['result'][0], conn)
            refund_info = change_purchase().new_refund_calculator(info_res[0]['result'][0], conn)
            #print(refund_info)
            #print("2")
            print("try here 1")
            print(refund_info)


            
            refund_amount = refund_info['refund_amount']
            print(refund_amount)
            if refund_amount > 0:
                print("2.3")
                # establishing more info for refund_info before we feed it in stripe_refund
                refund_info['refund_amount'] = abs(refund_amount)
                print("2.33")
                refund_info['purchase_uid'] = purchaseID
                print("2.36")
                print(refund_info)
                refund_info['refunded_id'] = change_purchase().stripe_refund(refund_info, conn)
                print("2.4")
                if refund_info['refunded_id'] is not None:
                    refunded = True
                else:
                    return {"message": "REFUND PROCESS ERROR."}, 500
            print("2.5")
            query = """
                    Update M4ME.purchases
                    set 
                        purchase_status = "CANCELLED and REFUNDED"
                    where purchase_uid = '""" + purchaseID + """';
                    """
            response = execute(query, 'post', conn)
            print("3")
            print(response)
            if response['code'] != 281:
                return {"message": "Internal Server Error"}, 500
            print("3.3")
            new_paymentId = get_new_paymentID(conn)
            print("3.4")
            if new_paymentId[1] == 500:
                print(new_paymentId[0])
                response['message'] = "Internal Server Error."
                return response, 500
            print("3.5")
            print(refund_amount)
            new_refund = 0-abs(refund_amount)
            
            new_refund = str(new_refund)
            print("3.6")
            #print(info_res["result"][2])
            print(type(new_refund))
            print(new_refund)
            #print(refund_info["refunded_id"][0])
            refund_id = str(refund_info["refunded_id"][0])
            #print(refund_id)
            print("3.65")
            print("start input")
            print(new_paymentId)
            print(purchaseID)
            print(new_refund)
            print(refund_id)
            print("end input")
            payment_query = """
                    insert into payments(payment_uid, payment_id, pay_purchase_uid, pay_purchase_id, payment_time_stamp, start_delivery_date, amount_due, amount_paid, charge_id, payment_type, cc_num, cc_exp_date, cc_cvv, cc_zip)
                    values(
                        '""" + new_paymentId + """',
                        '""" + new_paymentId + """',
                        '""" + purchaseID + """',
                        (
                            select purchase_id
                            from purchases
                            where purchase_uid = '""" + purchaseID + """'
                            order by purchase_date desc
                            limit 1
                        ),
                        now(),
                        now(),
                        '""" + new_refund + """',
                        '""" + new_refund + """',
                        '""" + refund_id + """',
                        "STRIPE",
                        (
                            select cc_num
                            from lplp
                            where purchase_uid = '""" + purchaseID + """'
                            order by payment_time_stamp desc
                            limit 1
                        ),
                        (
                            select cc_exp_date
                            from lplp
                            where purchase_uid = '""" + purchaseID + """'
                            order by payment_time_stamp desc
                            limit 1
                        ),
                        (
                            select cc_cvv
                            from lplp
                            where purchase_uid = '""" + purchaseID + """'
                            order by payment_time_stamp desc
                            limit 1
                        ),
                        (
                            select cc_zip
                            from lplp
                            where purchase_uid = '""" + purchaseID + """'
                            order by payment_time_stamp desc
                            limit 1
                        )
                    );
                    """
            print("3.7", payment_query)
            response2 = execute(payment_query, 'post', conn)
            print("4")
            print(response2)
            if response2['code'] != 281:
                return {"message": "Internal Server Error"}, 500
            print("before api reset")
            print(temp_key)
            if temp_key is not None:
                stripe.api_key = temp_key
            return response2

        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)


# Only for Web applications.  Mobile applications handles stripe directly from Mobile App
class Stripe_Intent(Resource):
    def post(self):
        response = {}

        #stripe.api_key = stripe_secret_test_key
        note = request.form.get('note')
        print(note, type(note))
        if note == "M4METEST":
            stripe.api_key = stripe_secret_test_key
            print('TEST')
        else:
            stripe.api_key = stripe_secret_live_key
            print('LIVE')

        if request.form.get('amount') == None:
            raise BadRequest('Request failed. Please provide the amount field.')
        try:
            amount = int(float(request.form.get('amount')) * 100)
        except:
            raise BadRequest('Request failed. Unable to convert amount to int')
        print('AMOUNT------', amount)

        intent = stripe.PaymentIntent.create(
        amount=amount,
        currency='usd',
        )
        print('INTENT------', intent)
        client_secret = intent.client_secret
        intent_id = intent.id
        response['client_secret'] = client_secret
        response['id'] = intent_id
        response['code'] = 200
        print(response['client_secret'])
        print(response['id'])
        return response


# Parva Code  ----------------------------------------------------------------------------------------------------------

### Code by Parva (copied in 040221)################################################################################

def sendAutopayEmails(email, start_delivery_date, id):

    try:
        msg = Message("Update Subscription", sender='support@mealsfor.me', recipients=[email])
        
        print('MESSAGE----', msg)
        print('message complete')
        
        msg.body =  "Hi,\n\n"\
                    "Thank you for orderding your meals from MTYD\n"\
                    "We want to let you know that we will be charging you for your next subscription which will start on "+start_delivery_date[:10]+".\n"\
                    "If you want to cancel this subscription please do it witihin 1 day of this email. \n\n"\
                    "Thx - MTYD Team"


        print('msg-bd----', msg.body)
        mail.send(msg)
        return 'successfull'
    except:
        print('error occured')
        return id
    
def couponsLogic(id, email, amount_due):
    try:
        print('in coupons logic')
        conn2 = connect()
        query = """
                SELECT * FROM M4ME.coupons;
                """
        print(query)
        items = execute(query, 'get', conn2)
        print(items['code'], type(items['code']))
        
        coupons = {}
        print('after coupons')
        print(items['result'])
        for vals in items['result']:
            if vals['email_id'] == 'delivery_email' or vals['email_id'] == '' or vals['email_id'] == None:
                print('1')
                print(float(vals['threshold']), float(amount_due))
                if float(vals['threshold']) <= float(amount_due):
                    print('2')
                    if vals['recurring'] == 'T' :
                        print('3')
                        if vals['limits'] != vals['num_used']:
                            print('4')
                            print(vals['expire_date'])
                            print(datetime.strptime(vals['expire_date'], "%Y-%m-%d %H-%M-%S"))
                            print(datetime.now())
                            if datetime.strptime(vals['expire_date'], "%Y-%m-%d %H-%M-%S") >= datetime.now():
                                print('5')
                                coupons[vals['coupon_uid']] = [vals['discount_percent'],vals['discount_amount'],vals['discount_shipping']]

        print('coupons', coupons)
        
        min_amt = amount_due
        min_amt_cp = ''
        for key, vals in coupons.items():
            tmp = amount_due
            if vals[0] > 0:
                tmp -= (vals[0]/100)*tmp
                
            if vals[1] > 0:
                tmp -= float(vals[1])

            if vals[2] > 0:
                tmp -= float(vals[2])
            
            tmp = round(tmp,2)
            if min_amt > tmp:
                min_amt_cp = key
                min_amt = tmp
    
        print(min_amt, min_amt_cp)
        if min_amt_cp != '':
            coupon_query = """UPDATE coupons SET num_used = num_used + 1
                                WHERE coupon_id =  """ + min_amt_cp + ";"
            res = execute(coupon_query, 'post', conn2)
        else:
            min_amt = 0
            min_amt_cp = ''
        
        return min_amt, min_amt_cp
    
    except:
        return 'error_except'
    finally:
        disconnect(conn2)

def createNewPurchase(id, start_delivery_date):
    # Implement coupons logic 
    # need zappa setting file to create cron job   
    try:
        print('IN createaccount')
        conn1 = connect()

        query = """
                SELECT *
                FROM M4ME.purchases as pur, M4ME.payments as pay
                WHERE pur.purchase_uid = '"""+ id +"""' AND pur.purchase_uid=pay.pay_purchase_uid;
                """
        items = execute(query, 'get', conn1)
        if items['code'] != 280:
            items['message'] = 'check sql query for new purchases'
            return id
        
        print('query done')
        data = items['result'][0]
        print('data loaded')
        
        customer_uid = data['pur_customer_uid']
        business_uid = data['business_uid'] if data.get('business_uid') is not None else 'NULL'
        delivery_first_name = data['delivery_first_name']
        delivery_last_name = data['delivery_last_name']
        delivery_email = data['delivery_email']
        delivery_phone = data['delivery_phone_num']
        delivery_address = data['delivery_address']
        delivery_unit = data['unit'] if data.get('unit') is not None else 'NULL'
        delivery_city = data['delivery_city']
        delivery_state = data['delivery_state']
        delivery_zip = data['delivery_zip']
        delivery_instructions = "'" + data['delivery_instructions'] + "'" if data.get('delivery_instructions') else 'NULL'
        delivery_longitude = data['delivery_longitude']
        delivery_latitude = data['delivery_latitude']
        items = "'" + str(data['items']) + "'"
        order_instructions = "'" + data['order_instructions'] + "'" if data.get('order_instructions') is not None else 'NULL'
        purchase_notes = "'" + data['purchase_notes'] + "'" if data.get('purchase_notes') is not None else 'NULL'
        amount_due = data['amount_due']
        amount_discount = data['amount_discount']
        amount_paid = data['amount_paid']
        service_fee = data['service_fee'] if data.get('service_fee') is not None else 0
        delivery_fee = data['delivery_fee'] if data.get('delivery_fee') is not None else 0
        driver_tip = data['driver_tip'] if data.get('driver_tip') is not None else 0
        taxes = data['taxes'] if data.get('taxes') is not None else 0
        subtotal = data['subtotal'] if data.get('subtotal') is not None else 0
        cc_num = data['cc_num']
        cc_exp_date = data['cc_exp_date']
        cc_cvv = data['cc_cvv']
        cc_zip = data['cc_zip']
        month = data['cc_exp_date'][5:7]
        year = data['cc_exp_date'][:4]
        
        print('data done')
        purchaseId = get_new_purchaseID(conn1)
        
        paymentId = get_new_paymentID(conn1)
        print('ids done')

        ##### check for coupons
        amount_due += service_fee + delivery_fee + driver_tip + taxes 
        rt = couponsLogic(id, delivery_email, amount_due)
        print(rt)
        amount_discount = amount_due - rt[0]
        coupon_id = rt[1]
        amount_due = rt[0]
        amount_must_paid = float(amount_due)
        print(amount_must_paid)
        print('coupon done')
        
        
        ###### create a token for stripe
        card_dict = {"number": data['cc_num'], "exp_month": int(month), "exp_year": int(year),"cvc": data['cc_cvv']}
        stripe_charge = {}
        try:
            card_token = stripe.Token.create(card=card_dict)
            print("2")
            if int(amount_must_paid) > 0:
                stripe_charge = stripe.Charge.create(
                    amount=int(round(amount_must_paid*100, 0)),
                    currency="usd",
                    source=card_token,
                    description="Charge customer for new Subscription")
            # update amount_paid. At this point, the payment has been processed so amount_paid == amount_due
            amount_paid = amount_due
        except stripe.error.CardError as e:
            # Since it's a decline, stripe.error.CardError will be caught
            response['message'] = e.error.message
            return response, 400
        
        print(stripe_charge)
        # update amount_paid. At this point, the payment has been processed so amount_paid == amount_due
        amount_paid = amount_due
        print('stripe done')
        charge_id = 'NULL' if stripe_charge.get('id') is None else stripe_charge.get('id')
        
        print('delivery done')
        
        ####### write into Payment and purchase table
        queries = [
                    '''
                    INSERT INTO M4ME.payments
                    SET payment_uid = \'''' + paymentId + '''\',
                        payment_id = \'''' + paymentId + '''\',
                        pay_purchase_uid = \'''' + purchaseId + '''\',
                        pay_purchase_id = \'''' + purchaseId + '''\',
                        payment_time_stamp = \'''' + str(getNow()) + '''\',
                        start_delivery_date = \'''' + str(start_delivery_date) + '''\',
                        pay_coupon_id = \'''' + coupon_id + '''\',
                        subtotal = \'''' + str(subtotal) + '''\',
                        amount_discount = \'''' + str(amount_discount) + '''\',
                        service_fee = \'''' + str(service_fee) + '''\',
                        delivery_fee = \'''' + str(delivery_fee) + '''\',
                        driver_tip = \'''' + str(driver_tip) + '''\',
                        taxes = \'''' + str(taxes) + '''\',
                        amount_due = \'''' + str(amount_due) + '''\',
                        amount_paid = \'''' + str(amount_paid) + '''\',
                        info_is_Addon = 'FALSE',
                        cc_num = \'''' + cc_num  + '''\', 
                        cc_exp_date = \'''' + cc_exp_date + '''\', 
                        cc_cvv = \'''' + cc_cvv + '''\', 
                        cc_zip = \'''' + cc_zip + '''\',
                        charge_id = \'''' + charge_id + '''\',
                        payment_type = 'STRIPE';
                    ''',
                    '''
                    INSERT INTO  M4ME.purchases
                    SET purchase_uid = \'''' + purchaseId + '''\',
                        purchase_date = \'''' + str(getNow()) + '''\',
                        purchase_id = \'''' + purchaseId + '''\',
                        purchase_status = 'ACTIVE',
                        pur_customer_uid = \'''' + str(customer_uid) + '''\',
                        delivery_first_name = \'''' + delivery_first_name + '''\',
                        delivery_last_name = \'''' + delivery_last_name + '''\',
                        delivery_email = \'''' + delivery_email + '''\',
                        delivery_phone_num = \'''' + delivery_phone + '''\',
                        delivery_address = \'''' + delivery_address + '''\',
                        delivery_unit = \'''' + delivery_unit + '''\',
                        delivery_city = \'''' + delivery_city + '''\',
                        delivery_state = \'''' + delivery_state + '''\',
                        delivery_zip = \'''' + delivery_zip + '''\',
                        delivery_instructions = \'''' + delivery_instructions + '''\',
                        delivery_longitude = \'''' + str(delivery_longitude) + '''\',
                        delivery_latitude = \'''' + delivery_latitude + '''\',
                        items = ''' + items + ''',
                        order_instructions = \'''' + order_instructions + '''\',
                        purchase_notes = \'''' + purchase_notes + '''\';
                        ''',
                        '''
                        UPDATE M4ME.purchases SET purchase_status = 'AutoPay' WHERE (purchase_uid = \'''' + id + '''\');
                        '''
                    ]
        print('queries')
        print(queries[0])
        print(queries[1])
        print(queries[2])
        response = simple_post_execute(queries, ["PAYMENTS", "PURCHASES", "purchase_status"], conn1)
        print('queries done')
        print(response)
        if response[1] == 201:
            response[0]['payment_id'] = paymentId
            response[0]['purchase_id'] = purchaseId
            print('correct response')
        else:
            if "paymentId" in locals() and "purchaseId" in locals():
                execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn1)
                execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchaseId + """';""", 'post', conn1)
                print('incorect response delete')
                return id
        
        return 'successfull'
    except:
        return id
    finally:
        disconnect(conn1)

class checkAutoPay(Resource):
    def get(self):

        def next_weekday(d, weekday):
            days_ahead = weekday - d.weekday()
            if days_ahead <= 0: # Target day already happened this week
                days_ahead += 7
            return d + timedelta(days_ahead)

        conn = connect()
        res = []
        fat_res = []

        delivery_days = ['mon', 'wed', 'fri']
        autoPay_days = ['tue', 'thu', 'sat']
        
        days_num = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        x = datetime.now()
        day_of_week = x.strftime("%a").lower()
        
        query = """
                SELECT pur.*, pay.*, ms.delivery_day
                FROM M4ME.purchases as pur, M4ME.payments as pay, M4ME.meals_selected as ms
                WHERE pur.purchase_status = 'ACTIVE' AND pur.purchase_uid=pay.pay_purchase_uid AND ms.sel_purchase_id = pur.purchase_uid
                GROUP BY pur.purchase_uid;
                """
        items = execute(query, 'get', conn)
        if items['code'] != 280:
            items['message'] = 'check sql query for purchases'
            return items
        
        
        for vals in items['result']:
            #------------------########
            cust_email = vals['delivery_email']
            
            if vals['purchase_uid'] != '400-000095':
                continue
            print('********#####TEST********#####', vals['purchase_uid'])
            sub_id = json.loads(vals['items'])
            query = """
                    SELECT sub.*
                    FROM M4ME.subscription_items sub
                    WHERE sub.item_uid = '"""+sub_id[0]['item_uid']+"""';
                    """
            
            items = execute(query,'get',conn)
            
            if items['code'] != 280:
                items['message'] = 'check sql query for sub id'
                return items
            
            freq = items['result'][0]['num_issues']

            start_delivery_date = vals['start_delivery_date']
            end_day = datetime.strftime(datetime.now(utc),"%Y-%m-%d")
            
            query = """
                    SELECT COUNT(delivery_day) AS skip_count FROM 
                    (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM M4ME.meals_selected
                        WHERE sel_purchase_id = '"""+vals['purchase_uid']+"""'
                        GROUP BY sel_menu_date) AS GB   #tells us which was last option customer selected
                        INNER JOIN M4ME.meals_selected S
                        ON S.sel_purchase_id = GB.sel_purchase_id
                            AND S.sel_menu_date = GB.sel_menu_date
                            AND S.selection_time = GB.max_selection_time
                    WHERE S.sel_menu_date >= '"""+start_delivery_date+"""'
                        AND S.sel_menu_date <= '"""+end_day+"""'
                        AND delivery_day = 'SKIP'
                    ORDER BY S.sel_menu_date;
                    """
            print(query)
            items = execute(query,'get',conn)
            
            if items['code'] != 280:
                items['message'] = 'check sql query for skips'
                return items
            
            skips = items['result'][0]['skip_count']
            print('skips',skips)
            start_delivery_date = datetime.strptime(start_delivery_date,'%Y-%m-%d %H-%M-%S').date()
            end_day = datetime.strptime(end_day,'%Y-%m-%d').date()
            delivered = (end_day - start_delivery_date).days//7 + 1 - skips

            print(delivered, freq, end_day - start_delivery_date)

            send_emails = []
            
            if delivered == freq:
                # if it's delivery day then just send emails
                # if it's autopay day then start charging
                d = datetime.now().date()
                
                if day_of_week[:3] in delivery_days:
                    #shoot email
                    idx = days_num.index(vals['delivery_day'].lower()[:3])
                    start_delivery_date = str(next_weekday(d, idx)) + " 00:00:00" # 0 = Monday, 1=Tuesday, 2=Wednesday...
                    
                    send_emails.append(sendAutopayEmails(cust_email, start_delivery_date, vals['purchase_uid']))
                
                elif day_of_week[:3] in autoPay_days:
                    #do autopay
                    idx = days_num.index(vals['delivery_day'].lower()[:3])
                    start_delivery_date = str(next_weekday(d, idx)) + " 00:00:00" # 0 = Monday, 1=Tuesday, 2=Wednesday...
                    res.append(createNewPurchase(vals['purchase_uid'], start_delivery_date))
                else:
                    continue

            elif delivered < freq:
                print('do nothing')
                continue
            
            else:
                #------------------########
                fat_res.append(vals['purchase_uid'])
                print('fatal error check database')
        
        print(res)
        
        # email error to prashant once cron job is done
        pay_er = ''
        for vals in res:
            if vals != 'successfull':
                pay_er += vals + ","
        pay_er = pay_er[:-1]
        if len(pay_er) == 0:
            pay_er = 'No Errors'
        
        print(fat_res)
        print(str(fat_res))

        if len(fat_res) == 0:
            fat_res = 'No Errors'

        
        email_er = ''
        for vals in send_emails:
            if vals != 'successfull':
                email_er += vals + ","
        email_er = email_er[:-1]
        if len(email_er) == 0:
            email_er = 'No Errors'

        
        # send email
        msg = Message("Errors in Cron job", sender='support@mealsfor.me', recipients=['parva.shah808@gmail.com'])
        #pmarathay@gmail.com
        print('MESSAGE----', msg)
        print('message complete')
        
        msg.body =  "Hi Prashant,\n\n"\
                    "This email contains errors if ANY after running cron job for emails and autopay in MTYD\n\n"\
                    "Ids where error occured: "+ pay_er +"\n\n"\
                    "Ids where FATAL error occured: "+ str(fat_res)+ "\n\n"\
                    "IDs where while sending email error occured: "+ email_er + "\n\n"\
                    "Check with backend guys if you run into any problems or have any questions.\n"\
                    "Thx - MTYD Team"
        
        print('msg-bd----', msg.body)
        mail.send(msg)
        disconnect(conn)
        
class adminInfo(Resource):

    def refund_calculator(self, info_res,  conn):
        print("in refund calculator")
        # Getting the original start and end date for requesting purchase
        start_delivery_date = datetime.strptime(info_res['start_delivery_date'], "%Y-%m-%d %H-%M-%S")
        # check for SKIP. Let consider the simple case. The customer can change their purchases if and only if their purchase
        # still active.
        week_remaining = int(info_res['payment_frequency'])

        end_delivery_date = start_delivery_date + timedelta(days=(week_remaining) * 7)
        skip_query = """SELECT COUNT(delivery_day) AS skip_count FROM
                            (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM meals_selected
                                WHERE sel_purchase_id = '""" + info_res['purchase_id'] + """'
                                GROUP BY sel_menu_date) AS GB
                                INNER JOIN meals_selected S
                                ON S.sel_purchase_id = GB.sel_purchase_id
                                    AND S.sel_menu_date = GB.sel_menu_date
                                    AND S.selection_time = GB.max_selection_time
                        WHERE S.sel_menu_date >= '""" + start_delivery_date.strftime("%Y-%m-%d %H-%M-%S") + """'
                            AND S.sel_menu_date <= '""" + datetime.now().strftime("%Y-%m-%d %H-%M-%S") + """'
                            AND delivery_day = 'SKIP'
                        ORDER BY S.sel_menu_date;
                    """
        skip_res = simple_get_execute(skip_query, "SKIP QUERY", conn)
        if skip_res[1] != 200:
            return skip_res
        skip = int(skip_res[0].get('skip_count')) if skip_res[0].get('skip_count') else 0
        if datetime.now().date() > start_delivery_date.date():
            delivered = (datetime.now().date() - start_delivery_date.date()).days//7 + 1 - skip
            week_remaining -= delivered
        elif (datetime.now().date() > end_delivery_date.date()):
            print("There is something wrong with the query to get info for the requested purchase.")
            response = {'message': "Internal Server Error."}
            return response, 500
        print("start here")
        print(info_res)
        item_price = json.loads(info_res['items'])[0].get('price')
        print("price is")
        print(item_price)
        customer_paid = float(item_price)
        print("paid amount is")
        print(customer_paid)
        print("end here")
        # get the price of the new item.
        items_query = """
                        SELECT * FROM subscription_items
                        WHERE item_name = '""" + info_res['item_name'] + """'
                        """
        items_res = simple_get_execute(items_query, "GET Subscription_items QUERY", conn)
        if items_res[1] != 200:
            return items_res
        price = {}
        for item in items_res[0]['result']:
            price[item['num_issues']] = item['item_price']
        
        print("price######", price)
        refund = 0
        if info_res['num_issues'] == 4: # 4 week prepaid
            print("matching 4 week pre-pay")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid - float(price[2]) - float(price[1])
            elif week_remaining == 2:
                refund = customer_paid - float(price[2])
            elif week_remaining == 3:
                refund = customer_paid - float(price[2])
            elif week_remaining == 4:
                refund = customer_paid
        elif info_res['num_issues'] == 2:
            print("matching 2 week Pre-pay")
            print("r0")
            if week_remaining == 0:
                refund = 0
                print("r1")
            elif week_remaining == 1:
                print("in price", price)
                refund = customer_paid - float(price[1])
                print("r2")
            elif week_remaining == 2:
                refund = customer_paid
                print("r3")
        elif info_res['num_issues'] == 1:
            print("matching weekly")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid
        return {"week_remaining": week_remaining, "refund_amount": refund}

    
    
    def get(self):
        
        conn  = connect()

        query = """
                SELECT * FROM M4ME.lplp;
                """
        items = execute(query, 'get', conn)

        if items['code'] == '281':
            items['message'] = "error check your query"
            return items

        #return items

        query_freq = """
                    SELECT item_uid, num_issues FROM M4ME.subscription_items;
                    """
        items_freq = execute(query_freq, 'get', conn)

        if items_freq['code'] == '281':
            items_freq['message'] = "error check your query"
            return items_freq
        
        uid_freq = items_freq["result"]
        uid_freq_dict = {}
        for item in uid_freq:
            uid_freq_dict[item["item_uid"]] = item["num_issues"]
        
        


        ans = []
        for vals in items['result']:
            
            item_uid = json.loads(vals["items"])[0]["item_uid"]
            vals["freq"] = uid_freq_dict[item_uid]

            if vals["purchase_status"] == "ACTIVE":
                purchaseID = vals["purchase_uid"]
                
                info_query = """
                        SELECT pur.*, pay.*, sub.*
                        FROM purchases pur, payments pay, subscription_items sub
                        WHERE pur.purchase_uid = pay.pay_purchase_uid
                            AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid
                                                    FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
                            AND pur.purchase_uid = '""" + purchaseID + """'
                            AND pur.purchase_status='ACTIVE';  
                        """
                print("info_query", info_query)
                info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
                print(info_res)
                if info_res[1] != 200:
                    return {"message": "Internal Server Error"}, 500
                # Calculate refund
                print("1.9")
                refund_info = self.refund_calculator(info_res[0]['result'][0], conn)
                vals["refund_amount"] = refund_info['refund_amount']
                
            else:
                vals["refund_amount"] = -1
            

            ans.append(vals)
        
        return ans

class test_cal(Resource):
    def get(self, purchaseID):
        
        conn = connect()
        info_query = """
                        SELECT pur.*, pay.*, sub.*
                        FROM purchases pur, payments pay, subscription_items sub
                        WHERE pur.purchase_uid = pay.pay_purchase_uid
                            AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid
                                                    FROM purchases WHERE purchase_uid = '""" + purchaseID + """')
                            AND pur.purchase_uid = '""" + purchaseID + """'
                            AND pur.purchase_status='ACTIVE';  
                        """
        print("info_query", info_query)
        info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
        print(info_res)
        if info_res[1] != 200:
            return {"message": "Internal Server Error"}, 500
        # Calculate refund
        print("1.9")
        refund_info = self.new_refund_calculator(info_res[0]['result'][0], conn)

        return refund_info



    def new_refund_calculator(self, info_res,  conn):


        print("in refund calculator")
        
        # checking skips new

        start_delivery_date = datetime.strptime(info_res['start_delivery_date'], "%Y-%m-%d %H-%M-%S")
        week_remaining = int(info_res['payment_frequency'])
        
        all_deliveries = """
                    SELECT COUNT(delivery_day) AS delivery_count FROM
                            (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM meals_selected
                                WHERE sel_purchase_id = '""" + info_res['purchase_id'] + """'
                                GROUP BY sel_menu_date) AS GB
                                INNER JOIN meals_selected S
                                ON S.sel_purchase_id = GB.sel_purchase_id
                                    AND S.sel_menu_date = GB.sel_menu_date
                                    AND S.selection_time = GB.max_selection_time
                    WHERE 
                        S.sel_menu_date >= '""" + start_delivery_date.strftime("%Y-%m-%d %H:%M:%S") + """'
                        AND S.sel_menu_date <= '""" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """'
                        AND delivery_day != 'SKIP'
                    ORDER BY S.sel_menu_date;
                    """
        print(all_deliveries)
        delivered_num = execute(all_deliveries, "get", conn)
        print(delivered_num)
        if delivered_num['code'] != 280:
            return delivered_num
        delivered_num = int(delivered_num['result'][0].get('delivery_count')) if delivered_num['result'][0].get('delivery_count') else 0
        print("delivered_num :", delivered_num)


        # get number of meals from item name
        num_meals = int(json.loads(info_res['items'])[0].get('name')[0])
        print("meals :",num_meals)
        # get number of days
        num_days = int(json.loads(info_res['items'])[0].get('qty'))
        
        print("days :", num_days)
        # get remaining days
        remaining_delivery_days = num_days - delivered_num 
        print("days reamin :",remaining_delivery_days)

        return remaining_delivery_days
        # if weeks remaining are 0 return 
        if remaining_delivery_days == 0:
            {"week_remaining": 0, "refund_amount": 0}


        # if remaining days are negative then it means there is some error 
        if remaining_delivery_days < 0:
            print("There is something wrong with the query to get info for the requested purchase.")
            response = {'message': "Internal Server Error."}
            return response, 500
        
        discount_query = """
                        SELECT * FROM M4ME.discounts;
                        """
        discount = execute(discount_query, 'get', conn)

        if discount['code'] != 280:
            return discount
        
        
        # get discount combinations in a dictionary
        discount_dict = {}
        for val in discount['result']:
            discount_dict[(val['num_deliveries'],val['num_meals'])] = float(val['total_discount'])
        
        customer_paid = 12*num_meals*num_days*(1-discount_dict[(num_days,num_meals)])

        customer_used_amount = 12*num_meals*delivered_num *(1-discount_dict[(delivered_num ,num_meals)])

        refund_amount = customer_paid - customer_used_amount

        return {"week_remaining": remaining_delivery_days, "refund_amount": float(str(round(refund_amount, 2)))}

### End of code by Parva ################################################################################





class createAccount2(Resource):
    def post(self):
        response = {}
        items = []
        try:
            conn = connect()
            data = request.get_json(force=True)
            print(data)
            email = data['email']
            firstName = data['first_name']
            lastName = data['last_name']
            # phone = data['phone_number']
            # address = data['address']
            # unit = data['unit'] if data.get('unit') is not None else 'NULL'
            # social_id = data['social_id'] if data.get('social_id') is not None else 'NULL'
            # city = data['city']
            # state = data['state']
            # zip_code = data['zip_code']
            # latitude = data['latitude']
            # longitude = data['longitude']
            referral = data['referral_source']
            role = data['role']
            cust_id = data['cust_id'] if data.get('cust_id') is not None else 'NULL'

            if data.get('social') is None or data.get('social') == "FALSE" or data.get('social') == False or data.get('social') == 'NULL':
                social_signup = False
            else:
                social_signup = True

            print(social_signup)
            get_user_id_query = "CALL new_customer_uid();"
            NewUserIDresponse = execute(get_user_id_query, 'get', conn)

            if NewUserIDresponse['code'] == 490:
                string = " Cannot get new User id. "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = "Internal Server Error."
                return response, 500
            NewUserID = NewUserIDresponse['result'][0]['new_id']

            if social_signup == False:

                salt = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

                password = sha512((data['password'] + salt).encode()).hexdigest()
                print('password------', password)
                algorithm = "SHA512"
                mobile_access_token = 'NULL'
                mobile_refresh_token = 'NULL'
                user_access_token = 'NULL'
                user_refresh_token = 'NULL'
                user_social_signup = 'NULL'
            else:

                mobile_access_token = data['mobile_access_token']
                mobile_refresh_token = data['mobile_refresh_token']
                user_access_token = data['user_access_token']
                user_refresh_token = data['user_refresh_token']
                salt = 'NULL'
                password = 'NULL'
                algorithm = 'NULL'
                user_social_signup = data['social']

                print('ELSE- OUT')

            if cust_id != 'NULL' and cust_id:

                NewUserID = cust_id

                query = '''
                            SELECT user_access_token, user_refresh_token, mobile_access_token, mobile_refresh_token 
                            FROM M4ME.customers
                            WHERE customer_uid = \'''' + cust_id + '''\';
                        '''
                it = execute(query, 'get', conn)
                print('it-------', it)

                if it['result'][0]['user_access_token'] != 'FALSE':
                    user_access_token = it['result'][0]['user_access_token']

                if it['result'][0]['user_refresh_token'] != 'FALSE':
                    user_refresh_token = it['result'][0]['user_refresh_token']

                if it['result'][0]['mobile_access_token'] != 'FALSE':
                    mobile_access_token = it['result'][0]['mobile_access_token']

                if it['result'][0]['mobile_refresh_token'] != 'FALSE':
                    mobile_refresh_token = it['result'][0]['mobile_refresh_token']

                customer_insert_query =  ['''
                                    UPDATE M4ME.customers 
                                    SET 
                                    customer_created_at = \'''' + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + '''\',
                                    customer_first_name = \'''' + firstName + '''\',
                                    customer_last_name = \'''' + lastName + '''\',
                                    customer_phone_num = \'''' + phone + '''\',
                                    password_salt = \'''' + salt + '''\',
                                    password_hashed = \'''' + password + '''\',
                                    password_algorithm = \'''' + algorithm + '''\',
                                    referral_source = \'''' + referral + '''\',
                                    role = \'''' + role + '''\',
                                    user_social_media = \'''' + user_social_signup + '''\',
                                    social_timestamp  =  DATE_ADD(now() , INTERVAL 14 DAY)
                                    WHERE customer_uid = \'''' + cust_id + '''\';
                                    ''']


            else:

                # check if there is a same customer_id existing
                query = """
                        SELECT customer_email FROM M4ME.customers
                        WHERE customer_email = \'""" + email + "\';"
                print('email---------')
                items = execute(query, 'get', conn)
                if items['result']:

                    items['result'] = ""
                    items['code'] = 409
                    items['message'] = "Email address has already been taken."

                    return items

                if items['code'] == 480:

                    items['result'] = ""
                    items['code'] = 480
                    items['message'] = "Internal Server Error."
                    return items


                # write everything to database
                customer_insert_query = ["""
                                        INSERT INTO M4ME.customers 
                                        (
                                            customer_uid,
                                            customer_created_at,
                                            customer_first_name,
                                            customer_last_name,
                                            password_salt,
                                            password_hashed,
                                            password_algorithm,
                                            referral_source,
                                            role,
                                            user_social_media,
                                            user_access_token,
                                            social_timestamp,
                                            user_refresh_token,
                                            mobile_access_token,
                                            mobile_refresh_token,
                                            social_id
                                        )
                                        VALUES
                                        (
                                        
                                            \'""" + NewUserID + """\',
                                            \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
                                            \'""" + firstName + """\',
                                            \'""" + lastName + """\',
                                            \'""" + salt + """\',
                                            \'""" + password + """\',
                                            \'""" + algorithm + """\',
                                            \'""" + referral + """\',
                                            \'""" + role + """\',
                                            \'""" + user_social_signup + """\',
                                            \'""" + user_access_token + """\',
                                            DATE_ADD(now() , INTERVAL 14 DAY),
                                            \'""" + user_refresh_token + """\',
                                            \'""" + mobile_access_token + """\',
                                            \'""" + mobile_refresh_token + """\',
                                            \'""" + social_id + """\');"""]
            print(customer_insert_query[0])
            items = execute(customer_insert_query[0], 'post', conn)

            if items['code'] != 281:
                items['result'] = ""
                items['code'] = 480
                items['message'] = "Error while inserting values in database"

                return items


            items['result'] = {
                'first_name': firstName,
                'last_name': lastName,
                'customer_uid': NewUserID,
                'access_token': user_access_token,
                'refresh_token': user_refresh_token,
                'access_token': mobile_access_token,
                'refresh_token': mobile_refresh_token,
                'social_id': social_id


            }
            items['message'] = 'Signup successful'
            items['code'] = 200

            print('sss-----', social_signup)
            return items

        except:
            print("Error happened while Sign Up")
            if "NewUserID" in locals():
                execute("""DELETE FROM customers WHERE customer_uid = '""" + NewUserID + """';""", 'post', conn)
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class brandAmbassador(Resource):

    def post(self, action):
        try:

            data = request.get_json(force=True)
            conn = connect()
            if not data.get('amb_email'):
                return 'Please enter ambassador email'
            query_amb = """
                    SELECT * FROM coupons
                    WHERE email_id = \'""" + data['amb_email'] + """\';
                    """
            items_amb = execute(query_amb, 'get', conn)

            if items_amb['code'] != 280:
                items_amb['message'] = 'No data available for this ambassador email'
                return items_amb

            if action == 'create_ambassador':
                
                for vals in items_amb['result']:
                    if vals['coupon_id'] == 'SFAmbassador':
                        return 'Customer already a Ambassador'
                
                # all check done, now make the custoamer a ambassador and issue them a coupon

                query = ["CALL new_coupons_uid;"]
                couponIDresponse = execute(query[0], 'get', conn)
                couponID = couponIDresponse['result'][0]['new_id']
                print('all checks done')
                dateObject = datetime.now()

                exp_date = dateObject.replace(year=dateObject.year + 5)
                exp_date = datetime.strftime(exp_date,"%Y-%m-%d %H:%M:%S")
                query = """
                INSERT INTO coupons 
                (coupon_uid, coupon_id, valid, discount_percent, discount_amount, discount_shipping, expire_date, limits, notes, num_used, recurring, email_id, cup_business_uid, threshold) 
                VALUES ( \'""" + couponID + """\', 'SFAmbassador', 'TRUE', '0', '10', '5', \'""" + exp_date + """\', '2', 'SFAmbassador', '0', 'F', \'""" + data['amb_email'] + """\', 'null', '5');
                """
                print(query)
                items = execute(query, 'post', conn)
                if items['code'] != 281:
                    items['message'] = "check sql query"
                    items['code'] = 400
                    return items


                items['message'] = 'SF Ambassdaor created'
                items['code'] = 200
                return items

            elif action == 'generate_coupon':

                # check if customer is already a ambassador because ambassador cannot refer himself or get referred
                query_cust = """
                    SELECT * FROM coupons
                    WHERE email_id = \'""" + data['cust_email'] + """\';
                    """
                items_cust = execute(query_cust, 'get', conn)
                for vals in items_cust['result']:
                    if vals['coupon_id'] == 'SFAmbassador':
                        return 'Customer himself is an Ambassador'


                flag = 0
                # check if ambassador exists
                for vals in items_amb['result']:
                    if vals['coupon_id'] == 'SFAmbassador':
                        flag = 1
                
                if flag == 0:
                    return 'No such Ambassador email exists'
                

                cust_email = data['cust_email']

                # customer can be referred only once so check that

                flag = 0
                for vals in items_cust['result']:
                    if vals['coupon_id'] == 'Referral':
                        flag = 1
                
                if flag == 1:
                    return 'Customer has already been refered in past'


                # generate coupon for refereed customer

                query = ["CALL new_coupons_uid;"]
                couponIDresponse = execute(query[0], 'get', conn)
                couponID = couponIDresponse['result'][0]['new_id']
                
                dateObject = datetime.now()
                exp_date = dateObject.replace(year=dateObject.year + 1)
                exp_date = datetime.strftime(exp_date,"%Y-%m-%d %H:%M:%S")
                query = """
                INSERT INTO coupons 
                (coupon_uid, coupon_id, valid, discount_percent, discount_amount, discount_shipping, expire_date, limits, notes, num_used, recurring, email_id, cup_business_uid, threshold) 
                VALUES ( \'""" + couponID + """\', 'Referral', 'TRUE', '0', '10', '5', \'""" + exp_date + """\', '2', 'Referral', '0', 'F', \'""" + cust_email + """\', 'null', '5');
                """
                print(query)
                items = execute(query, 'post', conn)
                if items['code'] != 281:
                    items['message'] = "check sql query"
                    return items

                # Now update ambasaddor coupon
                print('updating amb')
                query = """
                        UPDATE coupons SET limits = limits + 2 
                        WHERE coupon_id = 'SFAmbassador' AND email_id = \'""" + data['amb_email'] + """\'
                        """
                items = execute(query, 'post', conn)
                if items['code'] != 281:
                    items['message'] = "check sql query"
                    return items
                items['message'] = 'customer and ambassador coupons generated'
                query2= """
                        select * from coupons
                        where coupon_uid = '""" + couponID + """';
                        """
                items2 = execute(query2, 'get', conn)
                if items2['code'] != 280:
                    items2['message'] = "check sql query"
                    return items
                items2['message'] = 'customer and ambassador coupons generated'
                return items2
            
            else:
                return 'enter correct option'
            
            


        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class orders_by_customers(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    select d_menu_date,
                            jt_name,
                            customer_first_name as First_Name,
                            customer_last_name as Last_Name,
                            customer_uid,
                            lplpibr_purchase_id,
                            sum(jt_qty) as Qty
                    FROM fcs_items_by_row
                    inner join customers
                        on customer_uid = lplpibr_customer_uid
                    group by jt_name, d_menu_date, lplpibr_customer_uid
                    order by d_menu_date, customer_uid, jt_name;
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "Order data selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class delivery_weekdays(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    select distinct menu_date, weekday(menu_date)
                    from menu
                    where menu_date > now();
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "delivery weekdays selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)




class favourite_food(Resource):
    
    def post(self, action):
        try:
            conn = connect()
            data = request.get_json(force=True)

            if action == 'get':

                query = """
                        SELECT favorites 
                        FROM customers 
                        WHERE customer_uid = \'""" + data['customer_uid'] + """\';
                        """
                items = execute(query, 'get', conn)

                if items['code'] != 280:
                    items['message'] = 'Check sql query'
                return items
            
            elif action == 'post':
                print(data)
                print("start q1 here")
                query1 = """
                        select favorites
                        from customers
                        where customer_uid = \'""" + data['customer_uid'] + """\';
                        """
                #print(query1)
                items1 = execute(query1, 'get', conn)
                print("check 1")
                print(items1)
                print("check 2")
                print(items1["result"][0]["favorites"])
                favorite = str(data['favorite']).replace("'", '"')
                print(favorite)
                if items1["result"][0]["favorites"] == None:
                    favorite = favorite
                else:
                    favorite=items1["result"][0]["favorites"]+ "," + favorite
                print("check 3")
                #favorite=items1["result"][0]["favorites"]+ "," + favorite
                print(favorite)
                query = """
                        UPDATE customers 
                        SET favorites = \'""" + favorite + """\'
                        WHERE (customer_uid = \'""" + data['customer_uid'] + """\');
                        """
                print(query)
                items = execute(query, 'post', conn)

                if items['code'] != 281:
                    items['message'] = 'Check sql query'
                return items
            elif action == 'update':
                print(data)
                favorite = str(data['favorite']).replace("'", '"')
                print(favorite)
                query = """
                        UPDATE customers 
                        SET favorites = \'""" + favorite + """\'
                        WHERE (customer_uid = \'""" + data['customer_uid'] + """\');
                        """
                print(query)
                items = execute(query, 'post', conn)

                if items['code'] != 281:
                    items['message'] = 'Check sql query'
                return items
            else:
                return 'choose correct option'
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class lplp_specific(Resource):
    def get(self, p_uid):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    select * from lplp
                    where pay_purchase_uid = \'""" + p_uid + """\';
                    """

            items = execute(query, 'get', conn)
            print(items)
            if items['code']!=280:
                items['message'] = "Failed"
                items['code'] = 404
                #return items
            if items['code']== 280:
                items['message'] = "infomation selected"
                items['code'] = 200
                #return items
            return items
            #return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


# Define API routes
# Customer APIs

#NEW BASE URL 
#https://kur4j57ved.execute-api.us-west-1.amazonaws.com/dev

#--------------------- Signup/ Login page / Change Password ---------------------#
#api.add_resource(SignUp, '/api/v2/signup')
#  * The "signup" endpoint accepts only POST request with appropriate named      #
#  parameters. Please check the documentation for the right format of those named#
#  parameters.                                                                   #
api.add_resource(Login,'/api/v2/login')
#  * The "Login" endpoint accepts only POST request with at least 2 parameters   #
# in its body. The first param is "email" and the second one is either "password"#
# or "refresh_token". We are gonna re-use the token we got from facebook or      #
# google for our site ahttps://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/meals_selected_specific?customer_uid=100-000334&purchase_id=400-000436&menu_date=2020-11-22+00:00:00 ogin, '/api/v2/apple_login', '/')
api.add_resource(Change_Password, '/api/v2/change_password')

api.add_resource(Reset_Password, '/api/v2/reset_password')
#--------------------------------------------------------------------------------#

#---------------------------- Select Meal plan pages ----------------------------#
# We can use the Plans endpoint (in the Admin endpoints section below) to get    #
# needed info.
#--------------------------------------------------------------------------------#

#------------- Checkout, Meal Selection and Meals Schedule pages ----------------#
api.add_resource(Meals_Selected, '/api/v2/meals_selected')
#  * The "Meals_Selected" only accepts GET request with one required parameters  #
# "customer_id".It will return the information of all selected meals and addons  #
# which are associated with the specific purchase. Modified to show specific     #
# means for specific date                                                        #
api.add_resource(Get_Upcoming_Menu, '/api/v2/upcoming_menu' )
#  * The "Get_Upcoming_Menu" only accepts GET request without required param.    #
# It will return the information of all upcoming menu items.                     #
api.add_resource(Get_Latest_Purchases_Payments, '/api/v2/customer_lplp')
#  * The "Get_Latest_Purchases_Payments" only accepts GET request with 1 required#
#  parameters ("customer_uid"). It will return the information of all current    #
#  purchases of the customer associated with the given customer_uid.
api.add_resource(Next_Billing_Date, '/api/v2/next_billing_date')
#  * The "next_Billing_Date" only accepts GET request with parameter named       #
#  "customer_uid". It will return the next billing charge information.           #
api.add_resource(Next_Addon_Charge, '/api/v2/next_addon_charge')
#  * The "next_addon_charge" only accepts GET request with required parameter    #
# named "purchase_uid". It will return the next addon charge information.        #
api.add_resource(AccountSalt, '/api/v2/accountsalt')
#  * The "accountsalt" endpoint accepts only GET request with one required param. #
#  It will return the information of password hashed and password salt for an     #
# associated email account.
api.add_resource(Checkout, '/api/v2/checkout')
#  * The "checkout" accepts POST request with appropriate parameters. Please read#
# the documentation for these parameters and its formats.                        #
##################################################################################
api.add_resource(Meals_Selection, '/api/v2/meals_selection')
#  * The "Meals_Selection" accepts POST request with appropriate parameters      #
#  Please read the documentation for these parameters and its formats.           #

#api.add_resource(Change_Purchase, '/api/v2/change_purchase')
# *The "Change_Purchase" accepts POST request with required JSON format. Please  #
# read the documentation to get the required format for that JSON object.        #

api.add_resource(Refund_Calculator, '/api/v2/refund_calculator')                 #
# * The "Refund endpoint accepts GET request with purchase_uid as required       #
# parameter.

api.add_resource(Update_Delivery_Info, '/api/v2/update_delivery_info')
#--------------------------------------------------------------------------------#

#********************************************************************************#
#*******************************  ADMIN APIs  ***********************************#
#---------------------------------   Subscriptions   ----------------------------#
api.add_resource(Plans, '/api/v2/plans')
#  * The "plans" endpoint accepts only get request with one required parameter.  #
#  It will return all the meal plans in the SUBSCRIPTION_ITEM table. The returned#
#  info contains all meal plans (which is grouped by item's name) and its        #
#  associated details.                                                           #
#--------------------------------------------------------------------------------#

#---------------------------- Create / Edit Menu pages ---------------------------#
api.add_resource(Menu, '/api/v2/menu')
#  * The "Menu" endpoint accepts GET, POST, and DELETE request. For GET request,  #
#  this endpoint does not need any parameters and returns all the menu's info.    #
#  For the POST request, we need the appropriate JSON format for request.         #
#  The DELETE request needs the "menu_uid" as the parameter in order to delete    #
# that associated record in the database.
api.add_resource(Meals, '/api/v2/meals')
#  * The "Meals" endpoint accepts GET, POST, and PUT request. For GET request,    #
#  this endpoint does not need any parameters and returns all the meals's info.   #
#  For the POST and PUT request, we need the appropriate JSON format for the      #
#  the request.                                                                   #
# NOTICE: Do we need the DELETE request for this endpoint?
#---------------------------------------------------------------------------------#

api.add_resource(Recipes, '/api/v2/recipes')
#  * The get_recipes endpoint accepts only get request and return all associate   #
#   info. This endpoint requires one parameter named "meal_uid".                  #
api.add_resource(Ingredients, '/api/v2/ingredients')
#  * The "Ingredients" endpoint accepts GET, POST, and PUT request. For GET       #
#  request, this endpoint does not need any parameters and returns all the meals's#
#  info. For the POST and PUT request, we need the appropriate JSON format for the#
#  the request.                                                                   #
# NOTICE: Do we need the DELETE request for this endpoint?                        #
api.add_resource(Measure_Unit, '/api/v2/measure_unit')
#  * The "Measure_Unit" endpoint accepts GET, POST, and PUT request. For GET
#  request, this endpoint does not need any parameters and returns all the        #
#  measure unit's info. For the POST and PUT request, we need the appropriate JSON#
#  format for the the request.                                                    #
# NOTICE: Do we need the DELETE request for this endpoint?                        #
#-------------------------------- Plan / Coupon pages ----------------------------#
#  * The user can access /api/v2/plans endpoint to get all Plans.                 #
#  * The "Coupons" endpoint accepts GET, POST, PUT and DELETE requestS. The GET   #
#  request does not require any parameter. POST, and PUT request require an       #
# appropriate JSON objects and the DELETE request requires "coupon_uid" as the    #
# required parameter.                                                             #
api.add_resource(Coupons, '/api/v2/coupons')
#---------------------------------------------------------------------------------#
#  * The Get_Orders_By_Purchase_id endpoint accepts only GET request without any  #
#  parameters.                                                                    #
api.add_resource(Ordered_By_Date, '/api/v2/ordered_by_date')
#  * The "Ingredients_Need accepts only get request and return all associate info.#
#  This endpoint does not require any parameter.                                  #
api.add_resource(Ingredients_Need, '/api/v2/ingredients_need')

#**********************************************************************************#


api.add_resource(AllMenus, '/api/v2/allMenus')

api.add_resource(Edit_Menu, '/api/v2/Edit_Menu')

api.add_resource(Edit_Meal, '/api/v2/Edit_Meal')

api.add_resource(MealCreation, '/api/v2/mealcreation')

api.add_resource(Edit_Recipe, '/api/v2/Edit_Recipe')

api.add_resource(Add_New_Ingredient, '/api/v2/Add_New_Ingredient')

api.add_resource(Profile, '/api/v2/Profile/<string:id>')

api.add_resource(Meals_Selected_Specific, '/api/v2/meals_selected_specific')

api.add_resource(UpdateProfile, '/api/v2/UpdateProfile')

api.add_resource(access_refresh_update, '/api/v2/access_refresh_update')

api.add_resource(token_fetch_update, '/api/v2/token_fetch_update/<string:action>')

api.add_resource(customer_info, '/api/v2/customer_info')

api.add_resource(Meal_Detail, '/api/v2/Meal_Detail/<string:date>')

api.add_resource(List_of_Meals, '/api/v2/List_of_Meals/<string:date>')

api.add_resource(Create_Group, '/api/v2/Create_Group')

#api.add_resource(Latest_SMS, '/api/v2/Latest_SMS')

#api.add_resource(Send_Notification, '/api/v2/Send_Notification')

api.add_resource(Send_Twilio_SMS, '/api/v2/Send_Twilio_SMS')

api.add_resource(get_recipes, '/api/v2/get_recipes/<string:meal_id>')

api.add_resource(update_recipe, '/api/v2/update_recipe')

api.add_resource(get_orders, '/api/v2/get_orders')

api.add_resource(get_supplys_by_date, '/api/v2/get_supplys_by_date')

api.add_resource(get_item_revenue, '/api/v2/get_item_revenue')

api.add_resource(get_total_revenue, '/api/v2/get_total_revenue')

api.add_resource(get_delivery_info, '/api/v2/get_delivery_info/<string:purchase_id>') 

api.add_resource(update_guid_notification, '/api/v2/update_guid_notification/<string:role>,<string:action>')

# api.add_resource(Categorical_Options, '/api/v2/Categorical_Options/<string:long>,<string:lat>') #NEED TO FIX, put it later, do we need it?

api.add_resource(getItems, '/api/v2/getItems') #NEED  TO FIX, 

api.add_resource(Refund, '/api/v2/Refund')

api.add_resource(CouponDetails, '/api/v2/couponDetails/<string:coupon_id>', '/api/v2/couponDetails')

api.add_resource(history, '/api/v2/history/<string:email>')

api.add_resource(purchase_Data_SF, '/api/v2/purchase_Data_SF') # seems to be the same as checkout

api.add_resource(addItems, '/api/v2/addItems/<string:action>') #check if theres something similar

api.add_resource(business_details_update, '/api/v2/business_details_update/<string:action>')

#needs to be checked
api.add_resource(orders_by_business, '/api/v2/orders_by_business')# fixed

api.add_resource(order_actions, '/api/v2/order_actions/<string:action>')

api.add_resource(admin_report, '/api/v2/admin_report/<string:uid>')

api.add_resource(Send_Notification, '/api/v2/Send_Notification/<string:role>')

api.add_resource(Get_Registrations_From_Tag, '/api/v2/Get_Registrations_From_Tag/<string:tag>')

api.add_resource(Update_Registration_With_GUID_iOS, '/api/v2/Update_Registration_With_GUID_iOS')

api.add_resource(Update_Registration_With_GUID_Android, '/api/v2/Update_Registration_With_GUID_Android')

api.add_resource(Get_Tags_With_GUID_iOS, '/api/v2/Get_Tags_With_GUID_iOS/<string:tag>')

#no need to verify below
api.add_resource(update_all_items, '/api/v2/update_all_items/<string:uid>')

api.add_resource(createAccount, '/api/v2/createAccount')

api.add_resource(email_verification, '/api/v2/email_verification')

api.add_resource(all_businesses, '/api/v2/all_businesses')

api.add_resource(pid_history, '/api/v2/pid_history/<string:pid>')

api.add_resource(UpdatePassword, '/api/v2/UpdatePassword')

#api.add_resource(AppleLogin, '/api/v2/AppleLogin', '/')

api.add_resource(AppleLogin, '/api/v2/apple_login', '/')

api.add_resource(Get_Upcoming_Menu_Date, '/api/v2/upcoming_menu_dates' )

api.add_resource(Change_Purchase_ID, '/api/v2/change_purchase_id')

api.add_resource(Update_Delivery_Info_Address, '/api/v2/Update_Delivery_Info_Address')

api.add_resource(report_order_customer_pivot_detail, '/api/v2/report_order_customer_pivot_detail/<string:report>,<string:uid>')

api.add_resource(create_recipe, '/api/v2/create_recipe')

api.add_resource(Latest_activity, '/api/v2/Latest_activity/<string:user_id>')

api.add_resource(Orders_by_Items, '/api/v2/Orders_by_Items' )

api.add_resource(Orders_by_Purchase_Id, '/api/v2/Orders_by_Purchase_Id' )

api.add_resource(AppleEmail, '/api/v2/AppleEmail', '/')

api.add_resource(Stripe_Payment_key_checker, '/api/v2/Stripe_Payment_key_checker')

api.add_resource(Paypal_Payment_key_checker, '/api/v2/Paypal_Payment_key_checker')

api.add_resource(Order_by_items_with_Date, '/api/v2/Order_by_items_with_Date/<string:date>')

api.add_resource(Orders_by_Purchase_Id_with_Date, '/api/v2/Orders_by_Purchase_Id_with_Date/<string:date>')

api.add_resource(Ingredients_Recipe_Specific, '/api/v2/Ingredients_Recipe_Specific/<string:recipe_uid>')

api.add_resource(add_new_ingredient_recipe, '/api/v2/add_new_ingredient_recipe')

api.add_resource(Delete_Recipe_Specific, '/api/v2/Delete_Recipe_Specific')

api.add_resource(Edit_Meal_Plan, '/api/v2/Edit_Meal_Plan')

api.add_resource(get_Fee_Tax, '/api/v2/get_Fee_Tax/<string:z_id>,<string:day>')

api.add_resource(Update_Fee_Tax, '/api/v2/Update_Fee_Tax')

api.add_resource(get_Zones, '/api/v2/get_Zones')

api.add_resource(Update_Zone, '/api/v2/Update_Zone')

api.add_resource(update_zones, '/api/v2/update_zones/<string:action>')

api.add_resource(meal_type, '/api/v2/meal_type')

api.add_resource(customer_infos, '/api/v2/customer_infos')

api.add_resource(payment_info, '/api/v2/payment_info/<string:p_id>')

api.add_resource(payment_info_history, '/api/v2/payment_info_history/<string:p_id>')

api.add_resource(Meals_Selected_pid, '/api/v2/Meals_Selected_pid')

api.add_resource(orders_by_business_specific, '/api/v2/orders_by_business_specific/<string:b_id>')

api.add_resource(Orders_by_Purchase_Id_with_Pid, '/api/v2/Orders_by_Purchase_Id_with_Pid/<string:p_id>')

api.add_resource(Orders_by_Purchase_Id_with_Pid_and_date, '/api/v2/Orders_by_Purchase_Id_with_Pid_and_date/<string:p_id>,<string:date>')

api.add_resource(Orders_by_Items_total_items, '/api/v2/Orders_by_Items_total_items')

api.add_resource(categoricalOptions, '/api/v2/categoricalOptions/<string:long>,<string:lat>')

api.add_resource(create_update_meals, '/api/v2/create_update_meals')

api.add_resource(cancel_purchase, '/api/v2/cancel_purchase')

api.add_resource(get_Zones_specific, '/api/v2/get_Zones_specific/<string:lat>,<string:llong>') #use categoricalOptions instead

api.add_resource(find_next_sat, '/api/v2/find_next_sat')

api.add_resource(payment_info_history_fixed, '/api/v2/payment_info_history_fixed/<string:p_uid>')

api.add_resource(Get_Latest_Purchases_Payments_with_Refund, '/api/v2/Get_Latest_Purchases_Payments_with_Refund')

api.add_resource(add_surprise, '/api/v2/add_surprise/<string:p_uid>')

api.add_resource(discount_percentage, '/api/v2/discount_percentage/<string:n_delivery>')

api.add_resource(change_purchase, '/api/v2/change_purchase/<string:purchaseID>')

api.add_resource(Stripe_Intent, '/api/v2/Stripe_Intent')

api.add_resource(createAccount2, '/api/v2/createAccount2')

api.add_resource(brandAmbassador, '/api/v2/brandAmbassador/<string:action>')

api.add_resource(orders_by_customers, '/api/v2/orders_by_customers')

api.add_resource(delivery_weekdays, '/api/v2/delivery_weekdays')

api.add_resource(favourite_food, '/api/v2/favourite_food/<string:action>')

#api.add_resource(Paypal_Payment_key_checker, '/api/v2/Paypal_Payment_key_checker')

api.add_resource(Copy_Menu, '/api/v2/Copy_Menu')

api.add_resource(lplp_specific, '/api/v2/lplp_specific/<string:p_uid>')


api.add_resource(checkAutoPay, '/api/v2/checkAutoPay')

api.add_resource(adminInfo, '/api/v2/adminInfo')

api.add_resource(test_cal, '/api/v2/test_cal/<string:purchaseID>')


# Run on below IP address and port
# Make sure port number is unused (i.e. don't use numbers 0-1023)
# lambda function at: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=2000)
    #app.run(host='0.0.0.0', port=2000)


