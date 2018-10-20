from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.views import View
from django.contrib.auth import authenticate, login
import django.db, random, string
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404

from tempfile import TemporaryFile
from urllib.parse import urlparse


from .models import Dataset, Distribution, Schema, Profile, BureauCode, Division, Office
from .forms import RegistrationForm, UploadBureauCodesCSVFileForm, UploadDatasetsCSVFileForm, NewDatasetFileForm, NewDatasetURLForm, DatasetForm, DistributionForm
from .utilities import bureau_import, dataset_import, file_downloader, schema_generator, import_languages

def random_str(length):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for i in range(length))

def index(request):
    return render(request, 'index.html')

@user_passes_test(lambda u: u.is_authenticated)
def dashboard(request):
    datasets = None
    if request.user.is_authenticated:
      datasets = list(Dataset.objects.filter(publisher = request.user.id))
    else:
        datasets = []
        keys = [
            'id',
            'title',
            'description',
            'tags',
            'modified',
            'publisher',
            'contactPoint',
            'accessLevel',
            'bureauCodeUSG',
            'programCodeUSG',
            'license',
        ]
        for i in range(1, 30):
            new_dataset = {}
            for key in keys:
                new_dataset[key] = random_str(5)
            datasets.append(new_dataset)

    return render(request, 'dashboard.html', {'datasets' : datasets})

def register(request):
    if request.method == "POST":
        # this is a POST request
        form = RegistrationForm(request.POST)
        if form.is_valid():
            profile = Profile.objects.create_user(request.POST['username'], request.POST['email'], request.POST['password'], BureauCode.objects.filter(id = request.POST['bureau']).first(), Division.objects.filter(id = request.POST['division']).first(), Office.objects.filter(id = request.POST['office']).first())
            profile.save()

            user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
            if user is not None:
                login(request, user)
                return HttpResponseRedirect('/dashboard/')
            else:
                # maybe we should redirect to invalid login page?
                # this shouldn't happen, however
                raise django.db.InternalError('Could not authenticate user')
        else:
            # If the form isn't valid, it will pass the form errors
            # through to the render function that returns below
            pass
    else:
        # this is a GET request
        form = RegistrationForm()
    return render(request, 'register.html', {'form':form})

@user_passes_test(lambda u: u.is_superuser)
def utilities(request):
    if request.method == "POST":
        # this is a POST request
        if 'import-bureaus' in request.POST:
            # Bureau import form submission
            bureaucodes_form = UploadBureauCodesCSVFileForm(request.POST, request.FILES)
            datasets_form = UploadDatasetsCSVFileForm()
            if bureaucodes_form.is_valid():
                if len(BureauCode.objects.all()) == 0:
                    bureau_import.bureau_import(request.FILES['file'])
                else:
                    bureaucodes_form.add_error('file', 'Bureau codes already exist. You must remove them before importing new codes')
            else:
                # invalid form - this should pass back through to the page (with errors attached?)
                pass
        elif 'delete-bureaus' in request.POST:
            # Bureau delete form submission
            BureauCode.objects.all().delete()
            return HttpResponseRedirect('/utilities/')
        elif 'import-datasets' in request.POST:
            # Dataset import form submission
            datasets_form = UploadDatasetsCSVFileForm(request.POST, request.FILES)
            bureaucodes_form = UploadBureauCodesCSVFileForm()
            if datasets_form.is_valid():
                    dataset_import.dataset_import(request.FILES['file'])
            else:
                # invalid form - this should pass back through to the page (with errors attached?)
                pass
        elif 'import-languages' in request.POST:
            # Languages import
            import_languages.import_languages()
            return HttpResponseRedirect('/utilities/')
    else:
        # this is a GET request
        bureaucodes_form = UploadBureauCodesCSVFileForm()
        datasets_form = UploadDatasetsCSVFileForm()
    return render(request, 'utilities.html', {'bureaucodes_form': bureaucodes_form, 'datasets_form': datasets_form})

def load_divisions(request):
    bureau_id = request.GET.get('bureau')
    divisions = Division.objects.filter(bureau=bureau_id).order_by('description')
    return render(request, 'divisions_dropdown_list_options.html', {'divisions': divisions})

def load_offices(request):
    division_id = request.GET.get('division')
    offices = Office.objects.filter(division=division_id).order_by('description')
    return render(request, 'offices_dropdown_list_options.html', {'offices': offices})

def new_dataset(request):
    if request.method == "POST":
        if 'url_submit' in request.POST:
            #creates the form from the request.
            url_form = NewDatasetURLForm(request.POST)
            file_form = NewDatasetFileForm()

            #Checks if the form is valid.
            if url_form.is_valid():
                #Grabs the url, username, and password.
                url = request.POST['url']
                username = request.POST['username']
                password = request.POST['password']
                #Attempts to download the file using the URL.
                try:
                    temp_file = file_downloader.file_downloader.download_temp(url,username,password)
                    if temp_file is None:
                        #otherwise, it failed to download the file.
                        url_form.add_error('url', 'The provided URL failed to be downloaded.')
                        pass
                    else:
                        #if is succeeds, it will generate the schema.
                        created_schema = schema_generator.schema_generator.build(temp_file,url)
                        temp_file.close()

                #If it raises an exception, it attached the exception as an error on the form.
                #The only exceptions that can be thrown are ones raised directly by the file_downloader class.
                except file_downloader.FailedDownloadingFileException as e:
                    url_form.add_error('url',str(e))
                #All of other exceptions are caught and handled.
                except:
                    url_form.add_error('url', 'An error occured while downloading the file')
            else:
                #if the form isn't valid, it passed back the form.
                pass
        #file form was submitted
        elif 'file_submit' in request.POST:
            url_form = NewDatasetURLForm()
            file_form = NewDatasetFileForm(request.POST, request.FILES)
            if file_form.is_valid():
                #if a file was submitted it grabs the file and stores a reference.
                file = request.FILES['file']
                if not file.name.lower().endswith(('.csv','.xlsx','.json')):
                    file_form.add_error(None, 'The provided file is not a supported type.')
                else:
                    created_schema = schema_generator.schema_generator.build(file,file.name)
        elif 'blank_submit' in request.POST:
            created_schema = ''
        #create shcema
        schema = Schema()
        schema.data = created_schema
        schema.save()
        #create distribution - BLANK
        distribution = Distribution()
        distribution.save()
        #create dataset
        dataset = Dataset()
        dataset.distribution = distribution
        dataset.schema = schema
        profile = Profile.objects.get(id=request.user.id)
        dataset.publisher = profile
        dataset.save()

        dataset_identifier_path = '/dataset/' + str(dataset.id)
        dataset.identifier = request.build_absolute_uri(dataset_identifier_path)
        if profile.bureau:
            dataset.bureauCode.add(profile.bureau)
        if profile.division:
            dataset.programCode.add(profile.division)
        dataset.save()
        return HttpResponseRedirect(dataset_identifier_path)
    else:
        url_form = NewDatasetURLForm()
        file_form = NewDatasetFileForm()

    return render(request, 'new_dataset.html', {'url_form':url_form, 'file_form':file_form})

def dataset(request, dataset_id=None):
    ds = get_object_or_404(Dataset, id=dataset_id)
    if ds.publisher.id is not request.user.id:
        # the user doesn't own this distribution, don't allow access
        return HttpResponse('Forbidden', status=403)
    if request.method == "POST":
        dataset_form = DatasetForm(instance=ds, data=request.POST)
        # this is a POST request
        if dataset_form.is_valid():
            # the form is valid - save it
                dataset_form.save()
        else:
            # the return below will display form errors
            pass
    else:
        # this is probably a GET request
        dataset_form = DatasetForm(instance=ds)
        dataset_form.fields['distribution'].queryset = Distribution.objects.filter(dataset=ds)

    return render(request, 'dataset.html', {'dataset_id':dataset_id, 'form':dataset_form})

def distribution(request, distribution_id=None):
    dn = get_object_or_404(Distribution, id=distribution_id)
    if dn.dataset.publisher.id is not request.user.id:
        # the user doesn't own this distribution, throw an HTTP unauthorized
        return HttpResponse('Unauthorized', status=401)

    if request.method == "POST":
        distribution_form = DistributionForm(instance=dn, data=request.POST)
        # this is a POST request
        if distribution_form.is_valid():
            # the form is valid - save it
            distribution_form.save()
        else:
            # the return below will display form errors
            pass
    else:
        # this is probably a GET request
        distribution_form = DistributionForm(instance=dn)
    return render(request, 'distribution.html', {'distribution_id':distribution_id, 'form':distribution_form})

