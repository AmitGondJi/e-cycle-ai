@app.route('/download_certificate/<int:req_id>')
def download_certificate(req_id):
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    data = conn.execute('''
        SELECT requests.*, users.username 
        FROM requests 
        JOIN users ON requests.user_id = users.id 
        WHERE requests.id = ?
    ''', (req_id,)).fetchone()
    conn.close()

    if not data or data['status'] != 'Recycled':
        return "Not Available"

    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()

    # BORDER
    pdf.set_line_width(2)
    pdf.rect(10, 10, 277, 190)

    # TITLE
    pdf.set_font("Arial", 'B', 32)
    pdf.cell(0, 30, "E-WASTE RECYCLING CERTIFICATE", ln=True, align='C')

    # NAME
    pdf.set_font("Arial", 'B', 26)
    pdf.cell(0, 20, data['username'].upper(), ln=True, align='C')

    # BODY
    pdf.set_font("Arial", '', 16)
    pdf.multi_cell(0, 10,
        f"Successfully recycled {data['item_name']}.\n"
        f"Your contribution helps save the environment",
        align='C'
    )

    # DATE
    pdf.ln(10)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%d %B %Y')}", align='C')

    output = pdf.output(dest='S').encode('latin-1')

    return send_file(
        io.BytesIO(output),
        mimetype='application/pdf',
        as_attachment=True,
        download_name='certificate.pdf'
    )