from django.urls import reverse
from azbankgateways import bankfactories, default_settings as settings
import random
import string

from django.urls.base import reverse_lazy

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.contrib.auth.views import LoginView
from django.views.generic import ListView, DetailView, View
from django.urls import reverse_lazy
from core.forms import CheckoutForm, CouponForm, RefundForm, PaymentForm

from core.models import Book, OrderBook, Order, Address, Payment, Coupon, Refund, UserProfile
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
# stripe.api_key = settings.STRIPE_SECRET_KEY
from core.views import BookDetailView
from django.shortcuts import render
from .serializers import BookSerializer, UserSerializer
from rest_framework.generics import ListAPIView, RetrieveAPIView
from django.contrib.auth.models import Permission, User
from core.models import Book
from .permissions import (
    IsAuthorOrReadOnly,
    IsStaffOrReadOnly,
    IsSuperUser,
    IsSuperUserOrStaffReadOnly,
)
# Create your views here.


class BookList(ListAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer


class BookDetail(RetrieveAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    permission_classes = (IsStaffOrReadOnly, IsAuthorOrReadOnly)


class UserList(ListAPIView):
    queryset = User.objects.all()

    serializer_class = UserSerializer
    permission_classes = (IsSuperUserOrStaffReadOnly,)


class UserDetail(RetrieveAPIView):
    # queryset = User.objects.all()
    def get_queryset(self):
        return User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (IsSuperUserOrStaffReadOnly,)





@login_required
def add_to_cart(request, slug):
    book = get_object_or_404(Book, slug=slug)
    order_book, created = OrderBook.objects.get_or_create(
        book=book,
        user=request.user,
        ordered=False
    )
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # check if the order book is in the order
        if order.books.filter(book__slug=book.slug).exists():
            order_book.quantity += 1
            order_book.save()
            messages.info(request, "تعداد کتاب ها آپدیت شد.")
            return redirect("core:order-summary")
        else:
            order.books.add(order_book)
            messages.info(request, "این کتاب به سبد خرید شما اضافه شد.")
            return redirect("core:order-summary")
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(
            user=request.user, ordered_date=ordered_date)
        order.books.add(order_book)
        messages.info(request, "این کتاب به سبد خرید شما اضافه شد.")
        return redirect("core:order-summary")


@login_required
def remove_from_cart(request, slug):
    book = get_object_or_404(Book, slug=slug)
    order_qs = Order.objects.filter(
        user=request.user,
        ordered=False
    )
    if order_qs.exists():
        order = order_qs[0]
        # check if the order book is in the order
        if order.books.filter(book__slug=book.slug).exists():
            order_book = OrderBook.objects.filter(
                book=book,
                user=request.user,
                ordered=False
            )[0]
            order.books.remove(order_book)
            order_book.delete()
            messages.info(request, "این کتاب از سبد خرید شما حذف شد.")
            return redirect("core:order-summary")
        else:
            messages.info(request, "این کتاب در سبد خرید شما وجود ندارد .")
            return redirect("core:product", slug=slug)
    else:
        messages.info(request, "شما سفارش فعالی ندارید.")
        return redirect("core:product", slug=slug)


@login_required
def remove_single_book_from_cart(request, slug):
    book = get_object_or_404(Book, slug=slug)
    order_qs = Order.objects.filter(
        user=request.user,
        ordered=False
    )
    if order_qs.exists():
        order = order_qs[0]
        # check if the order book is in the order
        if order.books.filter(book__slug=book.slug).exists():
            order_book = OrderBook.objects.filter(
                book=book,
                user=request.user,
                ordered=False
            )[0]
            if order_book.quantity > 1:
                order_book.quantity -= 1
                order_book.save()
            else:
                order.books.remove(order_book)
            messages.info(request, "تعداد کتاب ها آپدیت شد.")
            return redirect("core:order-summary")
        else:
            messages.info(request, "این کتاب در سبد خرید شما وجود ندارد ")
            return redirect("core:product", slug=slug)
    else:
        messages.info(request, "شما سفارش فعالی ندارید. ")
        return redirect("core:product", slug=slug)


def get_coupon(request, code):
    try:
        coupon = Coupon.objects.get(code=code)
        return coupon
    except ObjectDoesNotExist:
        messages.info(request, "این کد تخفیف وجود ندارد.")
        return redirect("core:checkout")


class AddCouponView(View):
    def post(self, *args, **kwargs):
        form = CouponForm(self.request.POST or None)
        if form.is_valid():
            try:
                code = form.cleaned_data.get('code')
                order = Order.objects.get(
                    user=self.request.user, ordered=False)
                order.coupon = get_coupon(self.request, code)
                order.save()
                messages.success(self.request, "کد تخفیف با موفیت اضافه شد .")
                return redirect("core:checkout")
            except ObjectDoesNotExist:
                messages.info(self.request, "شما سفارش فعالی ندارید. ")
                return redirect("core:checkout")


class RequestRefundView(View):
    def get(self, *args, **kwargs):
        form = RefundForm()
        context = {
            'form': form
        }
        return render(self.request, "request_refund.html", context)

    def post(self, *args, **kwargs):
        form = RefundForm(self.request.POST)
        if form.is_valid():
            ref_code = form.cleaned_data.get('ref_code')
            message = form.cleaned_data.get('message')
            email = form.cleaned_data.get('email')
            # edit the order
            try:
                order = Order.objects.get(ref_code=ref_code)
                order.refund_requested = True
                order.save()

                # store the refund
                refund = Refund()
                refund.order = order
                refund.reason = message
                refund.email = email
                refund.save()

                messages.info(self.request, "درخواست شما دریافت شد.")
                return redirect("core:request-refund")

            except ObjectDoesNotExist:
                messages.info(self.request, "این کتاب وجود ندارد.")
                return redirect("core:request-refund")


class CheckoutView(View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            form = CheckoutForm()
            context = {
                'form': form,
                'couponform': CouponForm(),
                'order': order,
                'DISPLAY_COUPON_FORM': True
            }

            shipping_address_qs = Address.objects.filter(
                user=self.request.user,
                address_type='S',
                default=True
            )
            if shipping_address_qs.exists():
                context.update(
                    {'default_shipping_address': shipping_address_qs[0]})

            billing_address_qs = Address.objects.filter(
                user=self.request.user,
                address_type='B',
                default=True
            )
            if billing_address_qs.exists():
                context.update(
                    {'default_billing_address': billing_address_qs[0]})
            return render(self.request, "checkout.html", context)
        except ObjectDoesNotExist:
            messages.info(self.request, "شما سفارش فعالی ندارید.")
            return redirect("core:checkout")

    def post(self, *args, **kwargs):
        form = CheckoutForm(self.request.POST or None)
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            if form.is_valid():

                use_default_shipping = form.cleaned_data.get(
                    'use_default_shipping')
                if use_default_shipping:
                    print("Using the defualt shipping address")
                    address_qs = Address.objects.filter(
                        user=self.request.user,
                        address_type='S',
                        default=True
                    )
                    if address_qs.exists():
                        shipping_address = address_qs[0]
                        order.shipping_address = shipping_address
                        order.save()
                    else:
                        messages.info(
                            self.request, "آدرس پستی پیس فرض در وجود ندارد")
                        return redirect('core:checkout')
                else:
                    shipping_address1 = form.cleaned_data.get(
                        'shipping_address')
                    shipping_address2 = form.cleaned_data.get(
                        'shipping_address2')
                    shipping_country = form.cleaned_data.get(
                        'shipping_country')
                    shipping_zip = form.cleaned_data.get('shipping_zip')

                    if is_valid_form([shipping_address1, shipping_country, shipping_zip]):
                        shipping_address = Address(
                            user=self.request.user,
                            street_address=shipping_address1,
                            apartment_address=shipping_address2,
                            country=shipping_country,
                            zip_code=shipping_zip,
                            address_type='S'
                        )
                        shipping_address.save()

                        order.shipping_address = shipping_address
                        order.save()

                        set_default_shipping = form.cleaned_data.get(
                            'set_default_shipping')
                        if set_default_shipping:
                            shipping_address.default = True
                            shipping_address.save()

                    else:
                        messages.info(
                            self.request, "لطفا همه فیلد های مربوط به آدرس را پر کنید . ")

                use_default_billing = form.cleaned_data.get(
                    'use_default_billing')
                same_billing_address = form.cleaned_data.get(
                    'same_billing_address')

                if same_billing_address:
                    billing_address = shipping_address
                    billing_address.pk = None
                    billing_address.save()
                    billing_address.address_type = 'B'
                    billing_address.save()
                    order.billing_address = billing_address
                    order.save()

                elif use_default_billing:
                    address_qs = Address.objects.filter(
                        user=self.request.user,
                        address_type='B',
                        default=True
                    )
                    if address_qs.exists():
                        billing_address = address_qs[0]
                        order.billing_address = billing_address
                        order.save()
                    else:
                        messages.info(
                            self.request, "آدرس پستی پیس فرض در وجود ندارد")
                        return redirect('core:checkout')
                else:
                    billing_address1 = form.cleaned_data.get(
                        'billing_address')
                    billing_address2 = form.cleaned_data.get(
                        'billing_address2')
                    billing_country = form.cleaned_data.get(
                        'billing_country')
                    billing_zip = form.cleaned_data.get('billing_zip')

                    if is_valid_form([billing_address1, billing_country, billing_zip]):
                        billing_address = Address(
                            user=self.request.user,
                            street_address=billing_address1,
                            apartment_address=billing_address2,
                            country=billing_country,
                            zip_code=billing_zip,
                            address_type='B'
                        )
                        billing_address.save()

                        order.billing_address = billing_address
                        order.save()

                        set_default_billing = form.cleaned_data.get(
                            'set_default_billing')
                        if set_default_billing:
                            billing_address.default = True
                            billing_address.save()

                    else:
                        messages.info(
                            self.request, "لطفا همه فیلد های مربوط به آدرس را پر کنید . ")

                payment_option = form.cleaned_data.get('payment_option')

                if payment_option == 'S':
                    return redirect('core:payment', payment_option='paypal')
                elif payment_option == 'P':
                    return redirect('core:payment', payment_option='paypal')
                else:
                    messages.warning(
                        self.request, "گزینه پرداخت را انتخاب کنید. ")
                    return redirect('core:checkout')
        except ObjectDoesNotExist:
            messages.warning(self.request, "شما سفارش فعالی ندارید.")
            return redirect("core:order-summary")


global amount


class PaymentView(View):

    def get(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        if order.billing_address:
            context = {
                'order': order,
                'DISPLAY_COUPON_FORM': False,
                'STRIPE_PUBLIC_KEY': settings.STRIPE_PUBLIC_KEY
            }
            userprofile = self.request.user.userprofile
            if userprofile.one_click_purchasing:
                # fetch the users card list
                cards = stripe.Customer.list_sources(
                    userprofile.stripe_customer_id,
                    limit=3,
                    object='card'
                )
                card_list = cards['data']
                if len(card_list) > 0:
                    # update the context with the default card
                    context.update({
                        'card': card_list[0]
                    })
            return render(self.request, "payment.html", context)
        else:
            messages.warning(
                self.request, "شما آدرسی را اضافه نکرده اید.")
            return redirect("core:checkout")

    def post(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        form = PaymentForm(self.request.POST)
        userprofile = UserProfile.objects.get(user=self.request.user)
        if form.is_valid():
            token = form.cleaned_data.get('stripeToken')
            save = form.cleaned_data.get('save')
            use_default = form.cleaned_data.get('use_default')

            if save:
                if userprofile.stripe_customer_id != '' and userprofile.stripe_customer_id is not None:
                    customer = stripe.Customer.retrieve(
                        userprofile.stripe_customer_id)
                    customer.sources.create(source=token)

                else:
                    customer = stripe.Customer.create(
                        email=self.request.user.email,
                    )
                    customer.sources.create(source=token)
                    userprofile.stripe_customer_id = customer['id']
                    userprofile.one_click_purchasing = True
                    userprofile.save()

            amount = int(order.get_total() * 100)

            try:

                if use_default or save:
                    # charge the customer because we cannot charge the token more than once
                    charge = stripe.Charge.create(
                        amount=amount,  # cents
                        currency="usd",
                        customer=userprofile.stripe_customer_id
                    )
                else:
                    # charge once off on the token
                    charge = stripe.Charge.create(
                        amount=amount,  # cents
                        currency="usd",
                        source=token
                    )

                # create the payment
                payment = Payment()
                payment.stripe_charge_id = charge['id']
                payment.user = self.request.user
                payment.amount = order.get_total()
                payment.save()

                # assign the payment to the order

                order_books = order.books.all()
                order_books.update(ordered=True)
                for book in order_books:
                    book.save()

                order.ordered = True
                order.payment = payment
                order.ref_code = create_ref_code()
                order.save()

                messages.success(self.request, "سفارش شما با موفقیت ثبت شد!")
                return redirect("/")

            except stripe.error.CardError as e:
                body = e.json_body
                err = body.get('error', {})
                messages.warning(self.request, f"{err.get('message')}")
                return redirect("/")

            except stripe.error.RateLimitError as e:
                # Too many requests made to the API too quickly
                messages.warning(self.request, "Rate limit error")
                return redirect("/")

            except stripe.error.InvalidRequestError as e:
                # Invalid parameters were supplied to Stripe's API
                print(e)
                messages.warning(
                    self.request, "پارامترهای نامعتبری وجود دارد.")
                return redirect("/")

            except stripe.error.AuthenticationError as e:
                # Authentication with Stripe's API failed
                # (maybe you changed API keys recently)
                messages.warning(self.request, "احراز هویت انجام نشده است!")
                return redirect("/")

            except stripe.error.APIConnectionError as e:
                # Network communication with Stripe failed
                messages.warning(self.request, "خطای شبکه")
                return redirect("/")

            except stripe.error.StripeError as e:
                # Display a very generic error to the user, and maybe send
                # yourself an email
                messages.warning(
                    self.request, "مشکلی پیش آمده است. هزینه ای از شما دریافت نشد. لطفا دوباره تلاش کنید.")
                return redirect("/")

            except Exception as e:
                # send an email to ourselves
                messages.warning(
                    self.request, "یک خطای جدی رخ داد. به ما اطلاع داده شده است.")
                return redirect("/")

        messages.warning(self.request, "اطلاعات نامعتبر دریافت شد.")
        return redirect("/payment/stripe/")
