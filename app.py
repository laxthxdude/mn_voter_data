from flask import Flask, render_template, request
from voter_election_report import voter_election_report

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    error = None
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        zip_code = request.form.get('zip_code')
        
        # Call the modified function
        report = voter_election_report(first_name=first_name, last_name=last_name, zip_code=zip_code)
        
        if "error" in report:
            error = report["error"]
        else:
            results = report["results"]
    
    return render_template('index.html', results=results, error=error)

if __name__ == '__main__':
    app.run(debug=True)