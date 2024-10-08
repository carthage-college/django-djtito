# -*- coding: utf-8 -*-

import argparse

import django
import requests
import sys
django.setup()
from django.conf import settings
from django.core import serializers
from djtito.catalog.models import Course


desc = "Takes a URL and grabs JSON data for processing"
parser = argparse.ArgumentParser(description=desc)
parser.add_argument(
    '-u',
    '--url',
    help="The URL that returns JSON data",
    dest='earl',
)


def main():
    """
    Shell script that manages data exported from Informix and imported into MySQL.

    URL structure:

    Physics
    https://app.carthage.edu/djmapache/api/catalog/UG23/PHY/
    ALL Undergraduate Courses
    https://app.carthage.edu/djmapache/api/catalog/UG23/
    All Graduate Courses
    https://app.carthage.edu/djmapache/api/catalog/GR23/

    Steps:

    1) execute destroy.py to dump the catalog.

    2) import the UG* courses:

    python bin/json_munger.py --url=https://app.carthage.edu/djmapache/api/catalog/UG23/?api_key=xx

    3) execute the following SQL incantation:

    update course_catalog set disc="" where dept="EDU";
    update course_catalog set disc="" where disc="MUS";
    update course_catalog set disc="" where disc="MGT";
    update course_catalog set disc="AHS" where crs_no like "AHS %";

    4) execute the GR* URL for EDU:

    python bin/json_munger.py --url=https://app.carthage.edu/djmapache/api/catalog/GR23/EDU/?api_key=xx

    execute the SQL incantation for EDU courses:

    update course_catalog set disc="MED" where dept="EDU" and disc="EDU";
    update course_catalog set disc="EDU" where dept="EDU" and disc="";

    5) execute the GR* URL FOR MUS:

    python bin/json_munger.py --url=https://app.carthage.edu/djmapache/api/catalog/GR23/MUS/?api_key=xx

    execute the SQL incantation for MUS courses:

    update course_catalog set disc="MMT" where dept="MUS" and disc="MUS";
    update course_catalog set disc="MUS" where dept="MUS" and disc="";

    6) execute the GR* URL for MGT

    python bin/json_munger.py --url=https://app.carthage.edu/djmapache/api/catalog/GR23/MGT/?api_key=xx

    execute the SQL incantation for MGT courses:

    update course_catalog set disc="MBD" where dept="BUS" and disc="MGT";
    update course_catalog set disc="MGT" where dept="MMK" and disc="";

    7) execute the GR* URL for ATH:

    python bin/json_munger.py --url=https://app.carthage.edu/djmapache/api/catalog/GR23/ATH/?api_key=xx

    update course_catalog set disc="MAT" where dept="_ATH" and disc="ATH";


    8) generate the PDF with the prince command:

    ssh ganymede.carthage.edu
    cd /d2/www/vhosts/carthage.edu/subdomains/ganymede/httpdocs/academics/catalog/print/

    /usr/local/bin/prince \
    https://app.carthage.edu/djtito/catalog/print/ -o catalog.pdf

    9) optionally, set up a cronjob that runs every five minutes:

    */5 * * * * /usr/local/bin/prince https://www.carthage.edu/academics/catalog/print/
    --output=/d2/livewhale/content/academics/catalog/print/catalog.pdf >> /dev/null 2>&1

    """
    response = requests.get(earl, headers={'Cache-Control': 'no-cache'})
    json_response = serializers.deserialize('json', response.text)
    # here we cycle through the objects and execute some updates
    for course in json_response:
        if course.object.max_hrs == course.object.min_hrs:
            course.object.credits = int(course.object.max_hrs)
        else:
            course.object.credits = '{0}-{1}'.format(
                int(course.object.min_hrs), int(course.object.max_hrs),
            )
        course.object.instructors = '{0} {1}'.format(course.object.firstname, course.object.lastname)
        if course.object.instructors in {'', ' '}:
            course.object.instructors = 'Staff'
        course.object.terms = course.object.txt
        course.object.id = None
        course.save(using='workday')
    # search for duplicates and concatenate instructors and terms
    # from duplicates and then remove them.
    unique_courses = Course.objects.using('workday').values_list(
        'crs_no', flat=True,
    ).distinct()

    fields = []
    for field in Course._meta.get_fields():
        fields.append(field.name)

    for crs_no in unique_courses:
        dupes = Course.objects.using('workday').filter(
            pk__in=Course.objects.using('workday').filter(
                crs_no=crs_no
            ).values_list(
                'id', flat=True,
            ),
        )
        terms = []
        if dupes:
            parent_course = dupes[0]
            # we put professors and terms in lists so we can check for
            # duplicates and sort alphabetically
            profis = [parent_course.instructors]
            # oddly, txt is missing from time to time and becomes None
            # which causes the join on sorted(terms) below to barf
            if parent_course.txt and parent_course.txt != '':
                terms.append(parent_course.txt)
            # skip the 0 index since that is the course we will update
            # while removing the other dupes
            for dupe in dupes[1:]:
                instructor = dupe.instructors
                if instructor not in profis:
                    profis.append(instructor)
                dupe_term = None
                if dupe.txt:
                    dupe_term = dupe.txt
                if dupe_term and dupe_term not in terms:
                    terms.append(dupe_term)
                dupe.delete()
            parent_course.instructors = ', '.join(sorted(profis))
            # cms database encoding is wack
            for attr in fields:
                try:
                    setattr(
                        parent_course, attr, getattr(parent_course, attr)
                    )
                except Exception:
                    pass
            # sometimes None comes through as a list item and join()
            # barfs on that so we remove it first
            for term in terms:
                if not term:
                    terms.remove(term)
            parent_course.terms = ', '.join(sorted(terms))
            try:
                parent_course.save(using='workday')
            except Exception as error:
                print(parent_course.id, '"{0}"'.format(parent_course.instructors), error)


if __name__ == '__main__':
    args = parser.parse_args()
    earl = args.earl

    if earl:
        sys.exit(main())
    else:
        print("You must provide a URL\n")
        parser.print_help()
        sys.exit()
