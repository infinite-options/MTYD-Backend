### START PRASHANT CODE ################################################################################

# PRASHANT NEXT BILLING DATE ATTEMPT
class predict_next_billing_date(Resource):

    def get(self, id):

        try:
            conn = connect()
            print("Inside predict class", id)

            # CUSTOMER QUERY 2A: LAST DELIVERY DATE - WITH NEXT DELIVERY DATE CALCULATION
            query = """
                SELECT *,
                    ADDDATE(menu_date, 1) AS next_billing_date
                FROM ( 
                    SELECT A.*,
                        sum(B.delivery) as cum_qty
                    FROM ( 
                        SELECT * ,
                            IF (delivery_day LIKE "SKIP", 0, 1) AS delivery,
                            json_unquote(json_extract(lplp.items, '$[0].qty')) AS num_deliveries
                        FROM M4ME.lplp
                        JOIN (
                            SELECT DISTINCT menu_date
                            FROM menu
                            -- WHERE menu_date > now()
                            ORDER BY menu_date ASC) AS md
                        LEFT JOIN M4ME.latest_combined_meal lcm
                        ON lplp.purchase_id = lcm.sel_purchase_id AND
                                md.menu_date = lcm.sel_menu_date
                        WHERE pur_customer_uid = '""" + id + """' 
                                AND purchase_status = "ACTIVE"
                                AND menu_date >= start_delivery_date)
                        AS A
                    JOIN (
                        SELECT * ,
                            IF (delivery_day LIKE "SKIP", 0, 1) AS delivery,
                            json_unquote(json_extract(lplp.items, '$[0].qty')) AS num_deliveries
                        FROM M4ME.lplp
                        JOIN (
                            SELECT DISTINCT menu_date
                            FROM menu
                            -- WHERE menu_date > now()
                            ORDER BY menu_date ASC) AS md
                        LEFT JOIN M4ME.latest_combined_meal lcm
                        ON lplp.purchase_id = lcm.sel_purchase_id AND
                                md.menu_date = lcm.sel_menu_date
                        WHERE pur_customer_uid = '""" + id + """' 
                                AND purchase_status = "ACTIVE"
                                AND menu_date >= start_delivery_date)
                        AS B
                    ON A.menu_date >= B.menu_date
                        AND A.purchase_uid = B.purchase_uid
                    GROUP BY A.menu_date,
                        A.purchase_uid
                    ) AS cum_del
                WHERE cum_del.num_deliveries = cum_del.cum_qty
                ORDER BY cum_del.purchase_uid;
            """

            next_billing_date = execute(query, 'get', conn)
            print("Next Billing Date: ", next_billing_date)

            return next_billing_date

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class calculator(Resource):

    # GETS ALL INFORMATION RELATED TO A PURCHASE ID INCLUDING PAYMENT AND SUBSCRIPTION INFO        
    def purchase_engine (self, pur_id):

        try:
            conn = connect()
            # pur_id = '400-000223'
            print("\nInside purchase_engine calculator", pur_id)

            # TO RETURN ALL INFO ASSOCIATED WITH A PARTICULAR PURCHASE UID OR PURCHASE ID

            query = """
                    SELECT pur.*, pay.*, sub.*
                    FROM purchases pur, payments pay, subscription_items sub
                    WHERE pur.purchase_uid = pay.pay_purchase_uid
                        AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid
                                                FROM purchases WHERE purchase_uid = '""" + pur_id + """')
                        AND pur.purchase_uid = '""" + pur_id + """'
                        AND pur.purchase_status='ACTIVE';  
                    """
            pur_details = execute(query, 'get', conn)
            print('\nPurchase Details from Purchase Engine: ', pur_details)
            return pur_details

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
    
    # DETERMINE NUMBER OF ACTUAL DELIVERIES MADE
    def deliveries_made (self, pur_id):
        try:
            conn = connect()
            print("\nInside number of deliveries made", pur_id)

            # GET NUMBER OF ACTUAL DELIVERIES MADE (REMOVING SKIPS)
            query = """
                # QUERY 7: NUMBER OF DELIVERIES ALREADY MADE        
                SELECT -- *,
                    purchase_uid,
                    purchase_id,
                    sum(delivery) as num_deliveries
                FROM ( 
                    SELECT * ,
                        IF (delivery_day LIKE "SKIP", 0, 1) AS delivery,
                        json_unquote(json_extract(lplp.items, '$[0].qty')) AS num_deliveries
                    FROM M4ME.lplp
                    JOIN (
                        SELECT DISTINCT menu_date
                        FROM menu
                        -- WHERE menu_date > now()
                        ORDER BY menu_date ASC) AS md
                    LEFT JOIN M4ME.latest_combined_meal lcm
                    ON lplp.purchase_id = lcm.sel_purchase_id AND
                            md.menu_date = lcm.sel_menu_date
                    WHERE purchase_uid = '""" + pur_id + """' 
                        AND menu_date >= lplp.start_delivery_date 	-- AFTER START DATE
                        AND menu_date <= now()) AS lplpmdlcm;		-- BEFORE TODAY
                """

            deliveries = execute(query, 'get', conn)
            print('Deliveries Made: ', deliveries)

            return deliveries

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)   
    
    # DETERMINE HOW MUCH SOMEONE SHOULD PAY IF SOMEONE SELECTS A NEW PLAN (WORKS FOR NEW PLAN SELECTION AND CONSUMED MEALS)
    def billing (self, items_uid, qty):
        print("\nInside billing calculator")
        try:
            conn = connect()
            print("Item_UID: ", items_uid)
            qty = str(qty)
            print("Number of Deliveries: ", qty)

            # GET ITEM PRICE
            query = """
                SELECT *
                FROM M4ME.subscription_items, M4ME.discounts
                WHERE item_uid = '""" + items_uid + """'
                    AND num_deliveries = '""" + qty + """';
                """

            price_details = execute(query, 'get', conn)
            print('Purchase Details from Purchase Engine: ', price_details)
            return price_details

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)    

    # CALCULATE REFUND
    def refund (self, pur_id):

        try:
            conn = connect()
            print("\nInside refund calculator", pur_id)
            # print("Item_UID: ", items_uid)
            # print("Number of Deliveries: ", qty)

            # GET CURRENT PURCHASE INFO - SEE WHAT THEY PAID (PURCHASE ENGINE)
            pur_details = calculator().purchase_engine(pur_id)
            print("\nPurchase_details from billing: ", pur_details)

            items_uid = json.loads(pur_details['result'][0]['items'])[0].get('item_uid')
            print("Item_UID: ", items_uid)
            num_deliveries = json.loads(pur_details['result'][0]['items'])[0].get('qty')
            print("Number of Deliveries: ", num_deliveries)
            subtotal = pur_details['result'][0]['subtotal']
            print("Customer Subtotal: ", subtotal)
            amount_discount = pur_details['result'][0]['amount_discount']
            print("Customer amount_discount: ", amount_discount)
            service_fee = pur_details['result'][0]['service_fee']
            print("Customer service_fee: ", service_fee)
            delivery_fee = pur_details['result'][0]['delivery_fee']
            print("Customer delivery_fee: ", delivery_fee)
            driver_tip = pur_details['result'][0]['driver_tip']
            print("Customer driver_tip: ", driver_tip)
            taxes = pur_details['result'][0]['taxes']
            print("Customer taxes ", taxes)
            ambassador_code = pur_details['result'][0]['ambassador_code']
            print("Customer ambassador_code: ", ambassador_code)
            amount_due = pur_details['result'][0]['amount_due']
            print("Customer amount_due: ", amount_due)
            amount_paid = pur_details['result'][0]['amount_paid']
            print("Customer amount_paid: ", amount_paid)
            charge_id = pur_details['result'][0]['charge_id']
            print("Customer charge_id: ", charge_id)
            delivery_instructions = pur_details['result'][0]['delivery_instructions']
            print("Customer delivery_instructions: ", delivery_instructions)


            # CALCULATE NUMBER OF DELIVERIES ALREADY MADE (DELIVERIES MADE)
            deliveries_made = calculator().deliveries_made(pur_id)
            print("\nReturned from deliveries_made: ", deliveries_made)
            completed_deliveries = deliveries_made['result'][0]['num_deliveries']
            print("Num of Completed Deliveries: ", completed_deliveries)


            # CALCULATE HOW MUCH OF THE PLAN SOMEONE ACTUALLY CONSUMED (BILLING)
            if completed_deliveries is None:
                completed_deliveries = 0
                print("completed_deliveries: ", completed_deliveries)
                total_used = 0
                print(total_used)
            else:
                # completed_deliveries > 0:
                # print("true")
                used = calculator().billing(items_uid, completed_deliveries)
                print("\nConsumed Subscription: ", used)
                item_price = used['result'][0]['item_price']
                print("Used Price: ", item_price)
                delivery_discount = used['result'][0]['delivery_discount']
                print("Used delivery_discount: ", delivery_discount)
                total_used = round((item_price * completed_deliveries) * (1 - (delivery_discount/100)),2)
                print("Total Used: ", total_used)


            # CALCULATE REFUND AMOUNT  -  NEGATIVE AMOUNT IS HOW MUCH TO CHARGE
            refund = round(subtotal - amount_discount - total_used,2)
            print("Meal Refund: ", refund)

            print(num_deliveries, completed_deliveries)
            ratio = (int(num_deliveries) - int(completed_deliveries))/int(num_deliveries)
            print (ratio)

            
            return {"purchase_uid"          :  pur_id,
                    "purchase_id"           :  pur_id,
                    "meal_refund"           :  refund,
                    "service_fee"           :  service_fee,
                    "delivery_fee"          :  delivery_fee,
                    "driver_tip"            :  round(driver_tip * ratio,2),
                    "taxes"                 :  taxes,
                    "ambassador_code"       :  round(ambassador_code * ratio,2),
                    "refund_amount"         :  refund + round(driver_tip * ratio,2) - round(ambassador_code * ratio,2),
                    "charge_id"             :  charge_id,
                    "delivery_instructions" :  delivery_instructions}

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    # CALCULATE REFUND - FOR DEBUG PURPOSES.  SHOULD BE SAME CODE
    def get (self, pur_id):

        try:
            conn = connect()
            print("\nInside refund calculator", pur_id)
            # print("Item_UID: ", items_uid)
            # print("Number of Deliveries: ", qty)

            # GET CURRENT PURCHASE INFO - SEE WHAT THEY PAID
            pur_details = calculator().purchase_engine(pur_id)
            print("\nPurchase_details from billing: ", pur_details)

            items_uid = json.loads(pur_details['result'][0]['items'])[0].get('item_uid')
            print("Item_UID: ", items_uid)
            num_deliveries = json.loads(pur_details['result'][0]['items'])[0].get('qty')
            print("Number of Deliveries: ", num_deliveries)
            subtotal = pur_details['result'][0]['subtotal']
            print("Customer Subtotal: ", subtotal)
            amount_discount = pur_details['result'][0]['amount_discount']
            print("Customer amount_discount: ", amount_discount)
            service_fee = pur_details['result'][0]['service_fee']
            print("Customer service_fee: ", service_fee)
            delivery_fee = pur_details['result'][0]['delivery_fee']
            print("Customer delivery_fee: ", delivery_fee)
            driver_tip = pur_details['result'][0]['driver_tip']
            print("Customer driver_tip: ", driver_tip)
            taxes = pur_details['result'][0]['taxes']
            print("Customer taxes ", taxes)
            ambassador_code = pur_details['result'][0]['ambassador_code']
            print("Customer ambassador_code: ", ambassador_code)
            amount_due = pur_details['result'][0]['amount_due']
            print("Customer amount_due: ", amount_due)
            amount_paid = pur_details['result'][0]['amount_paid']
            print("Customer amount_paid: ", amount_paid)
            charge_id = pur_details['result'][0]['charge_id']
            print("Customer charge_id: ", charge_id)
            delivery_instructions = pur_details['result'][0]['delivery_instructions']
            print("Customer delivery_instructions: ", delivery_instructions)


            # CALCULATE NUMBER OF DELIVERIES ALREADY MADE
            deliveries_made = calculator().deliveries_made(pur_id)
            print("\nReturned from deliveries_made: ", deliveries_made)
            completed_deliveries = deliveries_made['result'][0]['num_deliveries']
            print("Num of Completed Deliveries: ", completed_deliveries)

            if completed_deliveries is None:
                completed_deliveries = 0
                print("completed_deliveries: ", completed_deliveries)
                total_used = 0
                print(total_used)
            else:
                # completed_deliveries > 0:
                # print("true")
                used = calculator().billing(items_uid, completed_deliveries)
                print("\nConsumed Subscription: ", used)
                item_price = used['result'][0]['item_price']
                print("Used Price: ", item_price)
                delivery_discount = used['result'][0]['delivery_discount']
                print("Used delivery_discount: ", delivery_discount)
                total_used = round((item_price * completed_deliveries) * (1 - (delivery_discount/100)),2)
                print("Total Used: ", total_used)


            # CALCULATE REFUND AMOUNT  -  NEGATIVE AMOUNT IS HOW MUCH TO CHARGE
            refund = round(subtotal - amount_discount - total_used,2)
            print("Meal Refund: ", refund)

            print(num_deliveries, completed_deliveries)
            ratio = (int(num_deliveries) - int(completed_deliveries))/int(num_deliveries)
            print (ratio)

            
            return {"purchase_uid"          :  pur_id,
                    "purchase_id"           :  pur_id,
                    "meal_refund"           :  refund,
                    "service_fee"           :  service_fee,
                    "delivery_fee"          :  delivery_fee,
                    "driver_tip"            :  round(driver_tip * ratio,2),
                    "taxes"                 :  taxes,
                    "ambassador_code"       :  round(ambassador_code * ratio,2),
                    "refund_amount"         :  refund + round(driver_tip * ratio,2) - round(ambassador_code * ratio,2),
                    "charge_id"             :  charge_id,
                    "delivery_instructions" :  delivery_instructions}

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


    # # PROCESS STRIPE REFUND
    # def stripe_refund (self, refund_info, conn):
    #         print("start stripe refund")
    #         refund_amount = refund_info['refund_amount']
    #         print("stripe 1")
    #         refund_id = []
    #         # retrieve charge info from stripe to determine how much refund amount left on current charge_id
    #         # if refund amount left on current charge_id < refund amount needed then trace back the latest previous payment
    #         # to get the next stripe_charge_id.
    #         #list all charge ids which are associated with current purchase_id
    #         query = '''SELECT charge_id from M4ME.payments
    #             WHERE pay_purchase_id = (SELECT pay_purchase_id FROM M4ME.payments
    #                                     WHERE pay_purchase_uid = "''' + refund_info['purchase_uid'] + '''")
    #                     ORDER BY payment_time_stamp DESC;'''
    #         res = simple_get_execute(query, "QUERY ALL CHARGE IDS FOR REFUND", conn)
    #         print(res)
    #         # print("res in stripe_refund: ", res)
    #         if not res[0]['result']:
    #             print("Cannot process refund. No charge id found")
    #             return {"message": "Internal Server Error"}, 500
    #         else:
    #             print ("stripe 2")
    #             #print(res[0]['result'][0]["charge_id"])
    #             # print(len(res[0]['result']))
    #             intx = 0
    #             charge_ids = {}
    #             inty = 0
    #             for intx in range(0,len(res[0]["result"])):
    #                 if res[0]["result"][intx]["charge_id"] is not None:
    #                     charge_ids[inty] = res[0]["result"][intx]["charge_id"]
    #                     inty=inty+1
    #             #print(charge_ids)
    #             print(charge_ids)
    #             #charge_ids = [v for item in res[0]['result'] for v in item.values() if v]
    #             #print("charge id " + charge_ids[intx])
    #             amount_should_refund = round(refund_amount*100,0)
    #             # print("before while loop. Charge_id: {}, its length: {}".format(charge_ids,len(charge_ids)))
    #             inty=inty-1
    #             while len(charge_ids) > 0 and amount_should_refund > 0 and charge_ids[inty] is not None:
    #                 print("amount should refund: ", amount_should_refund)
    #                 print("stripe3")
    #                 print(len(charge_ids))
    #                 #process_id = charge_ids.pop(0)
    #                 process_id = charge_ids[inty]
    #                 inty = inty - 1
    #                 print(charge_ids)
    #                 # print("processing id: ", process_id)
    #                 # print("charge_ids: {}, its  length: {}".format(charge_ids, len(charge_ids)))
    #                 #retrieve info from stripe for specific charge_id:
    #                 print("during stripe: stripe 1")
    #                 #print(stripe.PaymentIntent.retrieve("pi_1IjDpmLMju5RPMEv95tJVSX0",))
    #                 print(process_id)
    #                 if process_id[:2] == "pi":
    #                     process_id = stripe.PaymentIntent.retrieve(process_id).get("charges").get("data")[0].get("id")
    #                     #print(refunded_info.get("charges").get("data")[0].get("id"))
    #                 print("before retrieve 1")
    #                 #refunded_info = stripe.Charge.retrieve("ch_1IfUBGLMju5RPMEveNCUVxn9",)
    #                 #print("before retrieve 2")
    #                 refunded_info = stripe.Charge.retrieve(process_id,)
    #                 print("stripe 2")
    #                 print(refunded_info.get("amount"))
    #                 print(refunded_info.get('amount_refunded'))
    #                 print("start inputs")
    #                 print(refunded_info['amount'])
    #                 print(refunded_info['amount_refunded'])
    #                 print("end inputs ")
    #                 # print("refunded_info: ", refunded_info)
    #                 # print("refunded_info.get('amount'): ", refunded_info.get('amount_refunded'))
    #                 if refunded_info.get('amount') is not None and refunded_info.get('amount_refunded') is not None:
    #                     amount_could_refund = round(float(refunded_info['amount'] - refunded_info['amount_refunded']),0)
    #                     print(amount_could_refund)
    #                     print(amount_should_refund)
    #                     if abs(amount_could_refund-amount_should_refund)<=2:
    #                         amount_should_refund = amount_could_refund
    #                     # print("amount_could_refund: ", amount_could_refund)
    #                     # print("amount_should_refund: ", amount_should_refund)
    #                     if amount_should_refund <= amount_could_refund:
    #                         # refund it right away => amount should be refund is equal refunded_amount
    #                         print("here")
    #                         try:
    #                             refund_res = stripe.Refund.create(
    #                                 charge=process_id,
    #                                 amount=int(amount_should_refund)
    #                             )
    #                         except stripe.error.CardError as e:
    #                             # Since it's a decline, stripe.error.CardError will be caught
    #                             response['message'] = e.error.message
    #                             return response, 400
    #                         # print("refund_res: ", refund_res)
    #                         amount_should_refund = 0
    #                     elif amount_could_refund==0:
    #                         print ("problem here")
    #                         continue
    #                     else:
    #                         # refund it and then calculate how much is left for amount_should_refund
    #                         try:
    #                             refund_res = stripe.Refund.create(
    #                                 charge=process_id,
    #                                 amount=int(amount_could_refund)
    #                             )
    #                             # print("before substraction")
    #                             # print(type(amount_should_refund))
    #                             # print(type(amount_could_refund))
    #                             amount_should_refund -= int(amount_could_refund)
    #                             # print("amount_should_refund after recalculate: ", amount_should_refund)
    #                         except stripe.error.CardError as e:
    #                             # Since it's a decline, stripe.error.CardError will be caught
    #                             response['message'] = e.error.message
    #                             return response, 400
    #                     refund_id.append(refund_res.get('id'))
    #                     #print("refund id is " + refund_id)
    #             return refund_id


# JAYDEVA
class change_purchase_pm (Resource):
    def put(self):
    
        # STEP 1 GET INPUT INFO (WHAT ARE THEY CHANGING FROM AND TO)

        # STEP 2 CALCULATE REFUND OR EXTRA CHARGE AMOUNT

        # STEP 3 PROCESS STRIPE

        # STEP 4 WRITE TO DATABASE
    
        return



class cancel_purchase_pm (Resource):
    def put(self, pur_uid):
        
        # STEP 1 GET INPUT INFO (WHAT ARE THEY CANCELLING)
        conn = connect()
        print("\nInside Cancel Purchase", pur_uid)

        # STEP 2 CALCULATE REFUND
        print("\nInside Caclculate Refund", pur_uid)
        refund = calculator().refund(pur_uid)
        print("\nPurchase_details from billing: ", refund)
        print("Refund details: ", refund['meal_refund'])

        # STEP 3 PROCESS STRIPE
        # GET ALL TRANSACTIONS ASSOCIATED WITH TEH PURCHASE UID
        print("\nInside Get All Transactions", pur_uid)
        query = """ 
                SELECT charge_id 
                FROM M4ME.payments
                WHERE pay_purchase_id = '""" + pur_uid + """'
                ORDER BY payment_time_stamp DESC;
                """
        response = execute(query, 'get', conn)
        if response['code'] != 280:
            return {"message": "Related Transaction Error"}, 500
        print("Related Puchase IDs: ", response['result'])
        print("Number of Related Puchase IDs: ", len(response['result']))






        # STEP 4 WRITE TO DATABASE 

        # UPDATE PAYMENT TABLE
        # INSERT NEW ROW WITH REFUND AMOUNT AND REFUND ID

        # FIND OLD PAYMENT ID SO ITS EASY TO REFERENCE WHICH PAYMENT WAS BEING REFUNDED
        query = """ 
                SELECT payment_id, pay_purchase_id
                FROM M4ME.payments
                WHERE pay_purchase_uid = '""" + pur_uid + """';
                """
        response = execute(query, 'get', conn)
        if response['code'] != 280:
            return {"message": "Payment Insert Error"}, 500
        print("Get Payment ID response: ", response)

        query = """
                INSERT INTO M4ME.payments
                SET payment_uid = '""" + get_new_paymentID(conn) + """',
                    payment_id = '""" + response['result'][0]['payment_id'] + """',
                    pay_purchase_uid = '""" + pur_uid + """',
                    pay_purchase_id = '""" + response['result'][0]['pay_purchase_id'] + """',
                    payment_time_stamp =  '""" + str(getNow()) + """',
                    subtotal = '""" + str(refund['meal_refund']) + """',
                    service_fee = '""" + str(refund['service_fee']) + """',
                    delivery_fee = '""" + str(refund['delivery_fee']) + """',
                    driver_tip = '""" + str(refund['driver_tip']) + """',
                    taxes = '""" + str(refund['taxes']) + """',
                    amount_due = '""" + str(refund['meal_refund'] + refund['service_fee'] + refund['delivery_fee'] +refund['driver_tip'] + refund['taxes']) + """',
                    amount_paid = '""" + str(refund['meal_refund'] + refund['service_fee'] + refund['delivery_fee'] +refund['driver_tip'] + refund['taxes']) + """',
                    ambassador_code = '""" + str(refund['ambassador_code']) + """',
                    charge_id = '""" + str(refund['charge_id']) + """';
                """        
                
                         
        response = execute(query, 'post', conn)
        print("Payments Update db response: ", response)
        if response['code'] != 281:
            return {"message": "Payment Insert Error"}, 500

        # UPDATE PURCHASE TABLE
        # query = """
        #         UPDATE M4ME.purchases
        #         SET purchase_status = "CANCELLED and REFUNDED"
        #         where purchase_uid = '""" + pur_uid + """';
        #         """
        # response = execute(query, 'post', conn)
        # print("Purchases Update db response: ", response)
        # if response['code'] != 281:
        #     return {"message": "Purchase Insert Error"}, 500
        # return

class update_db (Resource):
    def update_purchase(self, purchase_uid):
        
        return

    def update_payment(self, payment_uid):

        return

    def insert_purchase(self):

        return

    def insert_payment(self):

        return

        












     
class cancel_purchase (Resource):
    def put(self):
        try:
            print("\nIn Cancel Purchase")
            conn = connect()
            data = request.get_json(force=True)
            print("Input JSON Data: ", data)
            pur_uid = data["purchase_uid"]
            print("Input Purchase ID: ", pur_uid)

            # STEP 1 CALL REFUND CALCULATOR TO SEE VALUE LEFT IN MEAL PLAN
            pur_details = calculator().refund(pur_uid)
            print("\nPurchase_details from billing: ", pur_details)
           
            meal_refund = pur_details['meal_refund']
            print("Customer meal_refund: ", meal_refund)
            service_fee = pur_details['service_fee']
            print("Customer service_fee: ", service_fee)
            delivery_fee = pur_details['delivery_fee']
            print("Customer delivery_fee: ", delivery_fee)
            driver_tip = pur_details['driver_tip']
            print("Customer driver_tip: ", driver_tip)
            taxes = pur_details['taxes']
            print("Customer taxes ", taxes)
            ambassador_code = pur_details['ambassador_code']
            print("Customer ambassador_code: ", ambassador_code)
            charge_id = pur_details['charge_id']
            print("Customer charge_id: ", charge_id)
            delivery_instructions = pur_details['delivery_instructions']
            print("Customer delivery_instructions: ", delivery_instructions)
            refund_amount = round(meal_refund + service_fee + delivery_fee + driver_tip + taxes + ambassador_code,2)
            print("Refund Amount: ", refund_amount)


            # STEP 2 GET STRIPE KEY TO BE ABLE TO CALL STRIPE
            print("\nGet Stripe Key")
            temp_key = ""
            if stripe.api_key is not None:
                temp_key = stripe.api_key
            stripe.api_key = get_stripe_key().get_key(delivery_instructions)
            print("Stripe Key: ", stripe.api_key)
            print ("For Reference, M4ME Stripe Key: sk_test_51HyqrgLMju5RPMEvowxoZHOI9...JQ5TqpGkl299bo00yD1lTRNK")


            # STEP 3 GET ALL PURCHASES ASSOCIATED WITH TRANSACTION
            print("\nGet Stripe Payment Intents")
            query = """
                SELECT charge_id 
                FROM M4ME.payments
                WHERE pay_purchase_id = (
                    SELECT pay_purchase_id 
                    FROM M4ME.payments
                    WHERE pay_purchase_uid = '""" + pur_uid + """')
                ORDER BY payment_time_stamp DESC;
            """
            res = simple_get_execute(query, "QUERY ALL CHARGE IDS FOR REFUND", conn)
            print("Return all stripe pi's: ",res)

            refund_id = []

            # STEP 4 PROCESS THE REFUND IN STRIPE
            # LEAVING CODE AS IS TO SEE IF THIS WORKS
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
                
                print(charge_ids)
                #charge_ids = [v for item in res[0]['result'] for v in item.values() if v]
                #print("charge id " + charge_ids[intx])

                refund_amount = 1 if pur_uid == "400-000003" else refund_amount
                print("\nRefund amount: ", refund_amount)
                amount_should_refund = round(refund_amount*100,0)
                print("Amount should refund: ", amount_should_refund)

                # print("before while loop. Charge_id: {}, its length: {}".format(charge_ids,len(charge_ids)))
                inty=inty-1
                while len(charge_ids) > 0 and amount_should_refund > 0 and charge_ids[inty] is not None:
                    print("amount should refund: ", amount_should_refund)
                    print("stripe3")
                    print(len(charge_ids))
                    #process_id = charge_ids.pop(0)
                    process_id = charge_ids[inty]
                    inty = inty - 1
                    print(charge_ids)
                    # print("processing id: ", process_id)
                    # print("charge_ids: {}, its  length: {}".format(charge_ids, len(charge_ids)))
                    #retrieve info from stripe for specific charge_id:


                    print("\nduring stripe: stripe 1")
                    #print(stripe.PaymentIntent.retrieve("pi_1IjDpmLMju5RPMEv95tJVSX0",))
                    print(process_id)
                    if process_id[:2] == "pi":
                        process_id = stripe.PaymentIntent.retrieve(process_id).get("charges").get("data")[0].get("id")
                        print("Stripe Process_ID: ", process_id)
                        #print(refunded_info.get("charges").get("data")[0].get("id"))


                    print("\nbefore retrieve 1")
                    #refunded_info = stripe.Charge.retrieve("ch_1IfUBGLMju5RPMEveNCUVxn9",)
                    #print("before retrieve 2")
                    refunded_info = stripe.Charge.retrieve(process_id,)
                    # print("Refunded Info: ", refunded_info)
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
                        if abs(amount_could_refund-amount_should_refund)<=2:
                            amount_should_refund = amount_could_refund
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
                        #print("refund id is " + refund_id)
                return refund_id

            # RETURN THE RETURN ID





            # return pur_details

            # # CALCULATE THE REFUND AMOUNT
            # if meal_refund > 0:
            #     refund_amount = abs(meal_refund + service_fee + delivery_fee + driver_tip + taxes + ambassador_code)
            #     print("Refund Amount: ", refund_amount)


            # https://huo8rhh76i.execute-api.us-west-1.amazonaws.com/dev/api/v2/refund 
            # {  
            #     "currency": "usd",   
            #     "customer_uid": "100-000009",
            #     "business_code": "M4METEST!",
            #     "refund_amount": "100",}






            # # CALCULATE REFUND INFO
            # print("try here 0")
            # #refund_info = Change_Purchase().refund_calculator(info_res[0]['result'][0], conn)
            # refund_info = change_purchase().new_refund_calculator(info_res[0]['result'][0], conn)
            # #print(refund_info)
            # #print("2")
            # print("try here 1")
            # print(refund_info)


            
            # refund_amount = refund_info['refund_amount']
            # print(refund_amount)
            # if refund_amount > 0:
            #     print("2.3")
            #     # establishing more info for refund_info before we feed it in stripe_refund
            #     refund_info['refund_amount'] = abs(refund_amount)
            #     print("2.33")
            #     refund_info['purchase_uid'] = purchaseID
            #     print("2.36")
            #     print(refund_info)
            #     refund_info['refunded_id'] = change_purchase().stripe_refund(refund_info, conn)
            #     print(refund_info['refunded_id'])
            #     print("2.4")
            #     if refund_info['refunded_id'] is not None:
            #         refunded = True
            #     else:
            #         return {"message": "REFUND PROCESS ERROR."}, 500
            # print("2.5")
            # query = """
            #         Update M4ME.purchases
            #         set 
            #             purchase_status = "CANCELLED and REFUNDED"
            #         where purchase_uid = '""" + purchaseID + """';
            #         """
            # response = execute(query, 'post', conn)
            # print("3")
            # print(response)
            # if response['code'] != 281:
            #     return {"message": "Internal Server Error"}, 500
            # print("3.3")
            # new_paymentId = get_new_paymentID(conn)
            # print("3.4")
            # if new_paymentId[1] == 500:
            #     print(new_paymentId[0])
            #     response['message'] = "Internal Server Error."
            #     return response, 500
            # print("3.5")
            # print(refund_amount)
            # new_refund = 0-abs(refund_amount)
            
            # new_refund = str(new_refund)
            # print("3.6")
            # #print(info_res["result"][2])
            # print(type(new_refund))
            # print(new_refund)
            # #print(refund_info["refunded_id"][0])
            # refund_id = str(refund_info["refunded_id"][0])
            # print(refund_id)
            # print("3.65")
            # print("start input")
            # print(new_paymentId)
            # print(purchaseID)
            # print(new_refund)
            # print(refund_id)
            # print("end input")
            # payment_query = """
            #         insert into payments(payment_uid, payment_id, pay_purchase_uid, pay_purchase_id, payment_time_stamp, start_delivery_date, amount_due, amount_paid, charge_id, payment_type, cc_num, cc_exp_date, cc_cvv, cc_zip)
            #         values(
            #             '""" + new_paymentId + """',
            #             '""" + new_paymentId + """',
            #             '""" + purchaseID + """',
            #             (
            #                 select purchase_id
            #                 from purchases
            #                 where purchase_uid = '""" + purchaseID + """'
            #                 order by purchase_date desc
            #                 limit 1
            #             ),
            #             now(),
            #             now(),
            #             '""" + new_refund + """',
            #             '""" + new_refund + """',
            #             '""" + refund_id + """',
            #             "STRIPE",
            #             (
            #                 select cc_num
            #                 from lplp
            #                 where purchase_uid = '""" + purchaseID + """'
            #                 order by payment_time_stamp desc
            #                 limit 1
            #             ),
            #             (
            #                 select cc_exp_date
            #                 from lplp
            #                 where purchase_uid = '""" + purchaseID + """'
            #                 order by payment_time_stamp desc
            #                 limit 1
            #             ),
            #             (
            #                 select cc_cvv
            #                 from lplp
            #                 where purchase_uid = '""" + purchaseID + """'
            #                 order by payment_time_stamp desc
            #                 limit 1
            #             ),
            #             (
            #                 select cc_zip
            #                 from lplp
            #                 where purchase_uid = '""" + purchaseID + """'
            #                 order by payment_time_stamp desc
            #                 limit 1
            #             )
            #         );
            #         """
            # print("3.7", payment_query)
            # response2 = execute(payment_query, 'post', conn)
            # print("4")
            # print(response2)
            # if response2['code'] != 281:
            #     return {"message": "Internal Server Error"}, 500
            # print("before api reset")
            # print(temp_key)
            # if temp_key is not None:
            #     stripe.api_key = temp_key
            # return response2

        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)









### END PRASHANT CODE ################################################################################