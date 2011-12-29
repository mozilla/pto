# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
# 
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
# 
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
# 
# The Initial Developer of the Original Code is Mozilla Corporation.
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
# 
# Contributor(s):
#   Peter Bengtsson <peterbe@mozilla.com>
# 
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
# 
# ***** END LICENSE BLOCK *****

import re
from django.conf import settings
from django.utils import formats
from django.core.validators import validate_email
from django import forms
from models import Hours, Entry
from users.models import UserProfile
import utils


class _BaseForm(object):
    def __init__(self, *args, **kwargs):
        date_format = kwargs.pop('date_format', settings.DEFAULT_DATE_FORMAT)
        super(_BaseForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            if isinstance(self.fields[field], forms.fields.DateField):
                klass = self.fields[field].widget.attrs.get('class')
                if klass:
                    klass += ' date'
                else:
                    klass = 'date'
                self.fields[field].widget.attrs['class'] = klass
                if 'size' not in self.fields[field].widget.attrs:
                    self.fields[field].widget.attrs['size'] = 30
                # Allow for all the default input formats AND our default one
                self.fields[field].input_formats = (
                  (date_format,) + formats.get_format('DATE_INPUT_FORMATS'))
                self.fields[field].widget.format = date_format

    def clean(self):
        cleaned_data = super(_BaseForm, self).clean()
        for field in cleaned_data:
            if isinstance(cleaned_data[field], basestring):
                cleaned_data[field] = (cleaned_data[field]
                                       .replace('\r\n', '\n')
                                       .strip())
        return cleaned_data


class BaseModelForm(_BaseForm, forms.ModelForm):
    pass


class BaseForm(_BaseForm, forms.Form):
    pass


class AddForm(BaseForm):
    start = forms.DateField(required=True)
    end = forms.DateField(required=True)
    details = forms.CharField(required=False,
                              widget=forms.widgets.Textarea(attrs={
                                'rows': 4,
                                'cols': 50
                              }))
    notify = forms.CharField(label="People to notify", required=False,
                             widget=forms.widgets.TextInput(attrs={
                               'size': 50
                             }))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(AddForm, self).__init__(*args, **kwargs)

    def clean_notify(self):
        value = self.cleaned_data['notify']
        emails = [x.strip() for x
                  in value.replace(',', ';').split(';')
                  if x.strip()]
        valid_emails = []
        for email in emails:
            # this might be in the form of
            #  'Peter Bengtsson <foo@email.com>'
            if (-1 < email.rfind('<') < email.rfind('@') < email.rfind('>')):
                try:
                    email = re.findall('<([\w\.\-]+@[\w\.\-]+)>', email)[0]
                except IndexError:
                    continue
                email = email.strip()
            try:
                validate_email(email)
            except forms.ValidationError:
                continue
            if email.lower() in settings.EMAIL_BLACKLIST:
                raise forms.ValidationError("Can't send email to %s" % email)
            valid_emails.append(email)
        return '; '.join(valid_emails)

    def clean(self):
        cleaned_data = super(AddForm, self).clean()
        if 'start' in cleaned_data and 'end' in cleaned_data:
            if cleaned_data['start'] > cleaned_data['end']:
                raise forms.ValidationError("Start can't be after end")
            # if all days are weekends, don't allow it
            start_day = cleaned_data['start'].strftime('%A')
            end_day = cleaned_data['end'].strftime('%A')
            weekends = set(['Sunday', 'Saturday'])
            days = set([start_day, end_day])
            # XXX: this needs a unit test
            if not (days - weekends):
                raise forms.ValidationError("Days are only weekend days")
        return cleaned_data


class HoursForm(BaseForm):
    def __init__(self, entry, *args, **kwargs):
        super(HoursForm, self).__init__(*args, **kwargs)
        self.entry = entry
        for date in utils.get_weekday_dates(self.entry.start, self.entry.end):
            field_name = date.strftime('d-%Y%m%d')

            try:
                hours_ = Hours.objects.get(date=date, entry__user=entry.user)
                help_text = ('Already logged %d hours on this day' %
                             hours_.hours)
            except Hours.DoesNotExist:
                help_text = ''
                hours_ = None

            choices = []
            choices.append((settings.WORK_DAY,
                            'Full day (%sh)' % settings.WORK_DAY))
            choices.append((settings.WORK_DAY / 2,
                            'Half day (%sh)' % (settings.WORK_DAY / 2)))
            choices.append((-1, 'Birthday'))
            if hours_:
                choices.append((0, '0 hrs'))

            self.fields[field_name] = forms.fields.ChoiceField(
              tuple(choices),
              required=True,
              label=date.strftime(settings.DEFAULT_DATE_FORMAT),
              widget=forms.widgets.RadioSelect(attrs={'class': 'hours'}),
              help_text=help_text,
            )

    def clean(self):
        cleaned_data = super(HoursForm, self).clean()
        dates = list(utils.get_weekday_dates(self.entry.start, self.entry.end))
        for date in dates:
            field_name = date.strftime('d-%Y%m%d')
            try:
                value = int(cleaned_data[field_name])
                if date == dates[0] and not value:
                    _search = dict(
                      start__gte=date,
                      end__gte=date,
                      user=self.entry.user
                    )
                    if not Entry.objects.filter(**_search).exists():
                        raise forms.ValidationError(
                           "First date can't be 0 hours")
                elif date == dates[-1] and not value:
                    raise forms.ValidationError("Last date can't be 0 hours")
            except (KeyError, ValueError):
                # something else is wrong and the clean method shouldn't
                # was called even though not all fields passed
                continue
        return cleaned_data


class ListFilterForm(BaseForm):
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    date_filed_from = forms.DateField(required=False)
    date_filed_to = forms.DateField(required=False)
    name = forms.CharField(required=False)
    country = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        super(ListFilterForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            if isinstance(self.fields[field], forms.fields.DateField):
                data_input = 'filed' if 'filed' in field else 'between'
                self.fields[field].widget.attrs.update({
                  'size': 12,
                  'autocomplete': 'off',
                  'data-input': data_input,
                })
        # insert the blank one
        self.fields['country'].choices = [('', 'Any country')]

        for each in (UserProfile.objects.exclude(country='')
                     .values('country')
                     .distinct('country')
                     .order_by('country')):
            country = each['country']
            self.fields['country'].choices.append((country, country))
